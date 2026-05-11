"""OpenAI tool-calling orchestration for Rico AI.

Reads OPENAI_API_KEY from the environment. Never hardcode API keys.
This module is additive and does not affect the existing daily pipeline.

HF free-mode fallback:
  When OpenAI is unavailable and HF_TOKEN/HF_API_KEY is present,
  a lightweight call to the Hugging Face Inference API is attempted.
  If HF also fails, a safe templated fallback is returned.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import requests

from src.rico_identity import get_rico_system_prompt
from src.rico_openai_runtime import (
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
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API")
        self.model = os.getenv("RICO_OPENAI_MODEL", "gpt-4.1-mini")
        self.tools = tools or {}
        self.safety = RicoSafetyGuard()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def hf_available(self) -> bool:
        """True when any HF key alias is set."""
        return bool(
            os.getenv("HF_API_KEY") or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")
        )

    def respond(self, user_message: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        safety = self.safety.check_message(user_message)
        if not safety.allowed:
            return {
                "type": "safety_refusal",
                "message": safety.safe_response,
                "category": safety.category,
            }

        if not self.available:
            # Try HF free inference before falling back to templated text
            if self.hf_available:
                hf_result = self._call_hf_free(user_message, user_context)
                if hf_result:
                    return hf_result
            return self._fallback_response()

        # Delegate to the minimal Responses API helper. Tools / structured
        # output / streaming are intentionally disabled until the prod call
        # is proven stable end-to-end (see PR description).
        profile_context = (
            json.dumps(user_context, ensure_ascii=False)
            if user_context else None
        )
        result = call_openai_minimal(user_message, profile_context=profile_context)

        if result.get("success"):
            return {
                "type": "openai_response",
                "message": result["text"],
                "model": result.get("model") or self.model,
                "provider": "openai",
            }

        # OpenAI failed — try HF free inference as secondary path
        if self.hf_available:
            hf_result = self._call_hf_free(user_message, user_context)
            if hf_result:
                return hf_result

        # Failure: surface structured diagnostics so the smoke endpoint and
        # chat response carry actionable error info.  Never include the API
        # key, raw exception headers, or the user's profile contents.
        return {
            "type": "openai_error_fallback",
            "message": result.get(
                "text",
                "Free mode is active. Rico can help set up your profile and guide your job search using free AI/fallback.",
            ),
            "error": result.get("error"),
            "error_detail": result.get("error_detail"),
            "openai_model": result.get("openai_model") or OPENAI_PRIMARY_MODEL,
            "fallback_model": result.get("fallback_model") or OPENAI_FALLBACK_MODEL,
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
        """Call a free Hugging Face inference model as a lightweight chat fallback.

        Returns None on failure so the caller can fall back to templated text.
        Never raises — all errors are caught and logged safely.
        """
        token = (
            os.getenv("HF_API_KEY", "").strip()
            or os.getenv("HF_TOKEN", "").strip()
            or os.getenv("HUGGINGFACE_API_KEY", "").strip()
        )
        if not token:
            return None

        # Use a reliable free-tier instruction model
        model = os.getenv("RICO_HF_MODEL", "HuggingFaceH4/zephyr-7b-beta")
        url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        system = (
            "You are Rico, a helpful job-search assistant for the UAE. "
            "Answer clearly, practically, and briefly."
        )
        context_str = json.dumps(user_context, ensure_ascii=False) if user_context else ""
        prompt = f"<|system|>\n{system}</s>\n\n{user_message}\nContext: {context_str}</s>\n<|assistant|>\n"

        try:
            r = requests.post(
                url,
                json={"inputs": prompt, "parameters": {"max_new_tokens": 250, "temperature": 0.7}},
                headers=headers,
                timeout=25,
            )
            if r.status_code == 429:
                logger.warning("hf_rate_limited")
                return None
            r.raise_for_status()
            data = r.json()
            # HF inference API returns [{"generated_text": "..."}] or list of strings
            if isinstance(data, list) and len(data) > 0:
                raw = data[0].get("generated_text", data[0]) if isinstance(data[0], dict) else data[0]
            elif isinstance(data, dict):
                raw = data.get("generated_text", "")
            else:
                raw = str(data)

            # Strip the prompt echo if present
            text = raw.split("<|assistant|>\n")[-1].strip() if "<|assistant|>" in raw else raw.strip()
            if not text:
                return None
            return {
                "type": "hf_response",
                "message": text,
                "provider": "huggingface",
                "model": model,
            }
        except Exception as exc:
            logger.warning(f"hf_fallback_failed error={exc}")
            return None

    def _fallback_response(self) -> Dict[str, Any]:
        return {
            "type": "fallback_response",
            "message": (
                "Free mode is active. Rico can help set up your profile and guide your job search using free AI/fallback."
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
