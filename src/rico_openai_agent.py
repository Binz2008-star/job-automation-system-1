"""Rico AI response layer.

Provider selection (via RICO_AI_PROVIDER env var):
  auto/unset    -- DeepSeek if configured, otherwise Hugging Face, otherwise fallback.
  hf            -- Hugging Face Inference API, zero OpenAI cost.
  openai        -- OpenAI API, opt-in only for premium mode.
  deepseek      -- DeepSeek API via the OpenAI-compatible SDK path.

When RICO_AI_PROVIDER=hf:
  - HF is called directly for rich replies.
  - OpenAI is never called regardless of OPENAI_API_KEY presence.
  - Templated fallback is used when HF is unavailable.

When RICO_AI_PROVIDER is unset:
  - DeepSeek is called if DEEPSEEK_API_KEY is present.
  - Otherwise HF is called if a HF key alias is present.
  - Templated fallback is used when neither is available.

When RICO_AI_PROVIDER=openai:
  - OpenAI is called if OPENAI_API_KEY is present.
  - HF is the cascade fallback.

When RICO_AI_PROVIDER=deepseek:
  - DeepSeek is called if DEEPSEEK_API_KEY is present.
  - HF is the cascade fallback.
  - Templated fallback if both fail.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from src.rico_env import get_ai_provider
from src.rico_identity import get_rico_system_prompt
from src.rico_openai_runtime import (
    DEEPSEEK_FALLBACK_MODEL,
    DEEPSEEK_PRIMARY_MODEL,
    OPENAI_FALLBACK_MODEL,
    OPENAI_PRIMARY_MODEL,
    call_openai_minimal,
)
from src.rico_safety import RicoSafetyGuard

logger = logging.getLogger(__name__)


@dataclass
class RicoToolResult:
    tool_name: str
    result: Dict[str, Any]


class RicoOpenAIAgent:
    """Rico reasoning layer using OpenAI Responses API when configured."""

    def __init__(self, tools: Optional[Dict[str, Callable[..., Dict[str, Any]]]] = None) -> None:
        # Canonical name is OPENAI_API_KEY. OPEN_AI_API is read as a temporary
        # fallback so existing Render deployments keep working until the env
        # var is renamed.
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API")
        self.api_key = self.openai_api_key  # backward-compatible alias used by older tests/callers
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.model = self._resolve_model()
        self.tools = tools or {}
        self.safety = RicoSafetyGuard()

    @property
    def available(self) -> bool:
        return self.openai_available or self.deepseek_available

    @property
    def openai_available(self) -> bool:
        return bool(self.openai_api_key or getattr(self, "api_key", None))

    @property
    def deepseek_available(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def hf_available(self) -> bool:
        """True when any HF key alias is set."""
        return bool(
            os.getenv("HF_API_TOKEN") or os.getenv("HF_API_KEY")
            or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")
        )

    @property
    def _use_openai(self) -> bool:
        """True only when operator explicitly opts in via RICO_AI_PROVIDER=openai."""
        return get_ai_provider() == "openai" and self.openai_available

    @property
    def _use_deepseek(self) -> bool:
        """True only when operator opts in to DeepSeek and the key is present."""
        return get_ai_provider() == "deepseek" and self.deepseek_available

    @property
    def provider_available(self) -> bool:
        provider = get_ai_provider()
        if provider == "openai":
            return self.openai_available
        if provider == "deepseek":
            return self.deepseek_available
        if provider == "huggingface":
            return self.hf_available
        return False

    def _resolve_model(self) -> str:
        provider = get_ai_provider()
        if provider == "deepseek":
            return os.getenv("RICO_DEEPSEEK_MODEL") or os.getenv("DEEPSEEK_MODEL") or DEEPSEEK_PRIMARY_MODEL
        if provider == "huggingface":
            return os.getenv("HF_TEXT_MODEL", "HuggingFaceH4/zephyr-7b-beta")
        return os.getenv("RICO_OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or OPENAI_PRIMARY_MODEL

    def respond(self, user_message: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        safety = self.safety.check_message(user_message)
        if not safety.allowed:
            return {
                "type": "safety_refusal",
                "message": safety.safe_response,
                "category": safety.category,
            }

        # Default path: HF is the primary provider (zero OpenAI cost)
        if not self._use_openai and not self._use_deepseek:
            if self.hf_available:
                hf_result = self._call_hf_free(user_message, user_context)
                if hf_result:
                    return hf_result
            return self._fallback_response()

        # Premium path: RICO_AI_PROVIDER=openai|deepseek explicitly set
        provider = "deepseek" if self._use_deepseek else "openai"
        profile_context = (
            json.dumps(user_context, ensure_ascii=False)
            if user_context else None
        )
        result = call_openai_minimal(
            user_message,
            profile_context=profile_context,
            provider=provider,
        )

        if result.get("success"):
            return {
                "type": f"{provider}_response",
                "message": result["text"],
                "model": result.get("model") or self.model,
                "provider": provider,
            }

        # Premium provider failed — cascade to HF
        if self.hf_available:
            hf_result = self._call_hf_free(user_message, user_context)
            if hf_result:
                return hf_result

        if result.get("is_rate_limited"):
            return {
                "type": f"{provider}_rate_limited",
                "message": result.get("text"),
                "provider": provider,
                "provider_state": "rate_limited",
                "response_source": "rate_limited",
            }

        model_key = "deepseek_model" if provider == "deepseek" else "openai_model"
        fallback_model = (
            result.get("fallback_model")
            or (DEEPSEEK_FALLBACK_MODEL if provider == "deepseek" else OPENAI_FALLBACK_MODEL)
        )

        return {
            "type": f"{provider}_error_fallback",
            "message": result.get(
                "text",
                "Free mode is active. Rico can help set up your profile and guide your job search.",
            ),
            "error": result.get("error"),
            "error_detail": result.get("error_detail"),
            model_key: result.get(model_key) or self.model,
            "fallback_model": fallback_model,
            "provider": "fallback",
        }

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> RicoToolResult:
        if tool_name not in self.tools:
            return RicoToolResult(tool_name, {"error": "tool_not_registered"})

        action_safety = self.safety.check_action(
            tool_name,
            user_has_approved=bool(arguments.get("user_has_approved")),
        )
        if not action_safety.allowed:
            return RicoToolResult(tool_name, {
                "error": "approval_required",
                "message": action_safety.safe_response,
                "required_user_confirmation": action_safety.required_user_confirmation,
            })

        return RicoToolResult(tool_name, self.tools[tool_name](**arguments))

    def _build_user_prompt(self, user_message: str, user_context: Optional[Dict[str, Any]]) -> str:
        context = json.dumps(user_context or {}, ensure_ascii=False, indent=2)
        return f"User message:\n{user_message}\n\nKnown Rico context:\n{context}"

    def _call_hf_free(
        self, user_message: str, user_context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Delegate to rico_hf_client.generate_text for a consistent, configurable HF call.

        Uses HF_TEXT_MODEL env var (default: HuggingFaceH4/zephyr-7b-beta).
        Returns None on failure so the caller can fall back to templated text.
        """
        from src.rico_hf_client import generate_text, is_available

        if not is_available():
            return None

        system = (
            "You are Rico, a helpful UAE job-search assistant. "
            "Answer clearly, practically, and briefly. "
            "Help users find jobs, prepare applications, and track opportunities in the UAE."
        )
        context_str = json.dumps(user_context, ensure_ascii=False) if user_context else ""
        prompt = f"{user_message}\nContext: {context_str}" if context_str else user_message

        model = os.getenv("HF_TEXT_MODEL", "HuggingFaceH4/zephyr-7b-beta")
        text = generate_text(prompt, system=system, max_new_tokens=300, model=model)
        if not text:
            return None
        return {
            "type": "hf_response",
            "message": text,
            "provider": "huggingface",
            "model": model,
        }

    def _fallback_response(self) -> Dict[str, Any]:
        return {
            "type": "fallback_response",
            "message": (
                "Free mode is active. Rico can help set up your profile and guide your job search using free AI/fallback tools. "
                "Advanced reasoning will activate after the configured AI provider is available."
            ),
            "provider": "fallback",
        }

    def _tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "search_jobs",
                "description": "Search UAE jobs for the user based on profile and preferences.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "city": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            },
            {
                "type": "function",
                "name": "update_preferences",
                "description": "Update Rico user preferences learned from chat.",
                "parameters": {
                    "type": "object",
                    "properties": {"preferences": {"type": "object"}},
                    "required": ["preferences"],
                },
            },
            {
                "type": "function",
                "name": "write_cover_letter",
                "description": "Draft a truthful cover letter for a selected job.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "tone": {"type": "string", "default": "professional"},
                        "user_has_approved": {"type": "boolean", "default": False},
                    },
                    "required": ["job_id"],
                },
            },
            {
                "type": "function",
                "name": "prepare_interview",
                "description": "Prepare interview notes and likely questions for a selected job.",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            },
            {
                "type": "function",
                "name": "track_application",
                "description": "Track application status and next follow-up step.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["job_id", "status"],
                },
            },
        ]
