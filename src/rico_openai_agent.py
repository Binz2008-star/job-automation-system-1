"""OpenAI tool-calling orchestration for Rico AI.

Reads OPENAI_API_KEY from the environment. Never hardcode API keys.
This module is additive and does not affect the existing daily pipeline.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from src.rico_identity import get_rico_system_prompt
from src.rico_openai_runtime import (
    OPENAI_FALLBACK_MODEL,
    OPENAI_PRIMARY_MODEL,
    call_openai_minimal,
)
from src.rico_safety import RicoSafetyGuard


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

    def respond(self, user_message: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        safety = self.safety.check_message(user_message)
        if not safety.allowed:
            return {
                "type": "safety_refusal",
                "message": safety.safe_response,
                "category": safety.category,
            }

        if not self.available:
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
            }

        # Failure: surface structured diagnostics so the smoke endpoint and
        # chat response carry actionable error info.  Never include the API
        # key, raw exception headers, or the user's profile contents.
        return {
            "type": "openai_error_fallback",
            "message": result.get(
                "text",
                "I understood. I can still help while the AI reasoning layer is being configured.",
            ),
            "error": result.get("error"),
            "error_detail": result.get("error_detail"),
            "openai_model": result.get("openai_model") or OPENAI_PRIMARY_MODEL,
            "fallback_model": result.get("fallback_model") or OPENAI_FALLBACK_MODEL,
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

    def _fallback_response(self) -> Dict[str, Any]:
        return {
            "type": "fallback_response",
            "message": (
                "I understand. I’ll use your profile, preferences, and actions to keep improving your UAE job search. "
                "Once OPENAI_API_KEY is configured, I can reason more deeply and call tools dynamically."
            ),
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
