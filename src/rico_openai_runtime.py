"""Minimal, stable Rico OpenAI runtime helper.

Restored to the simplest possible Responses API surface so we can prove the
call works in production before re-enabling tools / structured output /
streaming. See production symptom: gpt-4o-mini returning InternalServerError
when the chat path used tool schemas.

Hard rules:
  * No tools.
  * No response_format / json schema.
  * No streaming.
  * No previous_response_id.
  * No custom metadata.
  * Profile context truncated to 1200 chars.
  * Errors returned as a structured dict — exception class name, truncated
    message, status_code, request_id. Never the API key, headers, or full
    profile contents.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

OPENAI_PRIMARY_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4.1-mini")

_FALLBACK_TEXT = (
    "Free mode is active. Rico can help set up your profile and guide your job search using free AI/fallback."
)
_RATE_LIMITED_TEXT = (
    "Rico's AI provider is currently rate-limited. "
    "This is temporary — please try again in a minute."
)
_PROFILE_CONTEXT_MAX_CHARS = 1200
_SMOKE_MAX_OUTPUT_TOKENS = 80
_DEFAULT_MAX_OUTPUT_TOKENS = 500
_ERROR_MESSAGE_MAX_CHARS = 500

# Defensive: redact anything that looks like an OpenAI key from echoed
# exception messages. SDK errors occasionally include the key (e.g. when the
# server replies with the raw Authorization header in the error body).
_KEY_LIKE_RE = __import__("re").compile(r"sk-[A-Za-z0-9_\-]{6,}")


def _redact_secrets(text: str) -> str:
    return _KEY_LIKE_RE.sub("sk-***REDACTED***", text or "")


def _api_key_present() -> bool:
    """True when either canonical or legacy env var name is set."""
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API"))


def _safe_openai_error(exc: Exception) -> Dict[str, Any]:
    """Extract only safe diagnostic fields from an OpenAI exception.

    Never returns headers, the request body, or the API key. The response
    object is read only for status_code and the x-request-id header — both
    routinely included in OpenAI support tickets.
    """
    status_code = getattr(exc, "status_code", None)
    request_id = getattr(exc, "request_id", None)

    response = getattr(exc, "response", None)
    if response is not None:
        status_code = status_code or getattr(response, "status_code", None)
        headers = getattr(response, "headers", None)
        if headers:
            try:
                request_id = request_id or headers.get("x-request-id")
            except Exception:  # headers may be a non-mapping in some SDK versions
                pass

    return {
        "error_type": exc.__class__.__name__,
        "message": _redact_secrets(str(exc))[:_ERROR_MESSAGE_MAX_CHARS],
        "status_code": status_code,
        "request_id": request_id,
    }


def _extract_response_text(response: Any) -> str:
    """Pull text out of a Responses API result without assuming SDK version."""
    text = getattr(response, "output_text", None)
    if text:
        return text.strip()

    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)

    return "\n".join(chunks).strip()


def _failure_payload(last_error: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "success": False,
        "type": "openai_error_fallback",
        "response_source": "fallback",
        "openai_available": _api_key_present(),
        "openai_model": OPENAI_PRIMARY_MODEL,
        "fallback_model": OPENAI_FALLBACK_MODEL,
        "error": last_error.get("error_type") if last_error else "UnknownOpenAIError",
        "error_detail": last_error,
        "text": _FALLBACK_TEXT,
    }


def _rate_limited_payload(last_error: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "success": False,
        "type": "openai_rate_limited",
        "response_source": "rate_limited",
        "provider": "openai",
        "provider_state": "rate_limited",
        "openai_available": _api_key_present(),
        "openai_model": OPENAI_PRIMARY_MODEL,
        "error": "RateLimitError",
        "error_detail": last_error,
        "text": _RATE_LIMITED_TEXT,
    }


def call_openai_minimal(
    user_message: str,
    profile_context: Optional[str] = None,
    *,
    smoke: bool = False,
) -> Dict[str, Any]:
    """Send the simplest possible Responses API call and return a flat dict.

    On success::

        {
            "success": True,
            "response_source": "openai",
            "model": <primary or fallback model name>,
            "text": <assistant text>,
            "openai_available": True,
            "profile_context_present": <bool>,
        }

    On failure (both models)::

        {
            "success": False,
            "type": "openai_error_fallback",
            "response_source": "fallback",
            "openai_available": <bool>,
            "openai_model": <primary>,
            "fallback_model": <fallback>,
            "profile_context_present": <bool>,
            "error": <exception class name>,
            "error_detail": {...} | None,
            "text": <safe templated reply>,
        }
    """

    profile_present = bool(profile_context)

    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover — import-time failure is rare
        last_error = _safe_openai_error(exc)
        logger.warning(
            "Rico OpenAI import failed", extra={"openai_error": last_error}
        )
        payload = _failure_payload(last_error)
        payload["profile_context_present"] = profile_present
        return payload

    try:
        client = OpenAI()
    except Exception as exc:
        # Most common: OPENAI_API_KEY missing → OpenAIError on construction.
        last_error = _safe_openai_error(exc)
        logger.warning(
            "Rico OpenAI client init failed",
            extra={"openai_error": last_error, "smoke": smoke},
        )
        payload = _failure_payload(last_error)
        payload["profile_context_present"] = profile_present
        return payload

    system_prompt = (
        "You are Rico, a helpful job-search assistant. "
        "Answer clearly, practically, and briefly."
    )

    final_user_message = "Say OK" if smoke else str(user_message or "")

    if profile_context and not smoke:
        safe_context = str(profile_context)[:_PROFILE_CONTEXT_MAX_CHARS]
        final_user_message = (
            "User profile context, summarized:\n"
            f"{safe_context}\n\n"
            "User message:\n"
            f"{final_user_message}"
        )

    last_error: Optional[Dict[str, Any]] = None

    for model in (OPENAI_PRIMARY_MODEL, OPENAI_FALLBACK_MODEL):
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": final_user_message},
                ],
                max_output_tokens=(
                    _SMOKE_MAX_OUTPUT_TOKENS if smoke else _DEFAULT_MAX_OUTPUT_TOKENS
                ),
            )

            text = _extract_response_text(response)
            if not text:
                raise RuntimeError("OpenAI response returned empty text")

            return {
                "success": True,
                "response_source": "openai",
                "model": model,
                "text": text,
                "openai_available": True,
                "profile_context_present": profile_present,
            }

        except Exception as exc:
            last_error = _safe_openai_error(exc)
            is_rate_limit = (
                last_error.get("status_code") == 429
                or "RateLimitError" in last_error.get("error_type", "")
            )
            logger.warning(
                "Rico OpenAI rate limited — skipping retry" if is_rate_limit else "Rico OpenAI call failed safely",
                extra={
                    "openai_error": last_error,
                    "model": model,
                    "smoke": smoke,
                    "profile_context_present": profile_present,
                },
            )
            if is_rate_limit:
                payload = _rate_limited_payload(last_error)
                payload["profile_context_present"] = profile_present
                payload["is_rate_limited"] = True
                return payload

    payload = _failure_payload(last_error)
    payload["profile_context_present"] = profile_present
    return payload
