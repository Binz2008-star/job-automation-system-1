"""Minimal, stable Rico AI runtime helper.

The module name is kept for backward compatibility, but the helper now supports
both:

  * OpenAI Responses API
  * DeepSeek OpenAI-compatible Chat Completions API

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

OPENAI_PRIMARY_MODEL = (
    os.getenv("RICO_OPENAI_MODEL")
    or os.getenv("OPENAI_MODEL")
    or "gpt-4o-mini"
)
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4.1-mini")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_PRIMARY_MODEL = (
    os.getenv("RICO_DEEPSEEK_MODEL")
    or os.getenv("DEEPSEEK_MODEL")
    or "deepseek-v4-flash"
)
DEEPSEEK_FALLBACK_MODEL = os.getenv("DEEPSEEK_FALLBACK_MODEL", "deepseek-v4-pro")

_FALLBACK_TEXT = (
    "Free mode is active. Rico can help set up your profile and guide your job search using free AI/fallback tools. "
    "Advanced reasoning will activate after the configured AI provider is available."
)
_RATE_LIMITED_TEXT = (
    "Rico's AI provider is currently rate-limited. "
    "This is temporary — please try again in a minute."
)
_PROFILE_CONTEXT_MAX_CHARS = 1200
_SMOKE_MAX_OUTPUT_TOKENS = 80
_DEFAULT_MAX_OUTPUT_TOKENS = 500
_ERROR_MESSAGE_MAX_CHARS = 500

# Defensive: redact anything that looks like an OpenAI/DeepSeek key from echoed
# exception messages. SDK errors occasionally include the key (e.g. when the
# server replies with the raw Authorization header in the error body).
_KEY_LIKE_RE = __import__("re").compile(r"(?:sk|dsk)-[A-Za-z0-9_\-]{6,}")


def _redact_secrets(text: str) -> str:
    return _KEY_LIKE_RE.sub("sk-***REDACTED***", text or "")


def _openai_key_present() -> bool:
    """True when either canonical or legacy OpenAI env var name is set."""
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API"))


def _deepseek_key_present() -> bool:
    """True when the DeepSeek API key is configured."""
    return bool(os.getenv("DEEPSEEK_API_KEY"))


def _provider_name(provider: Optional[str]) -> str:
    selected = (provider or "openai").strip().lower()
    return "deepseek" if selected == "deepseek" else "openai"


def _provider_key_present(provider: str) -> bool:
    return _deepseek_key_present() if provider == "deepseek" else _openai_key_present()


def _provider_models(provider: str) -> tuple[str, str]:
    if provider == "deepseek":
        return DEEPSEEK_PRIMARY_MODEL, DEEPSEEK_FALLBACK_MODEL
    return OPENAI_PRIMARY_MODEL, OPENAI_FALLBACK_MODEL


def _provider_key(provider: str) -> Optional[str]:
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY")
    return os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API")


def _safe_openai_error(exc: Exception) -> Dict[str, Any]:
    """Extract only safe diagnostic fields from an OpenAI-compatible exception.

    Never returns headers, the request body, or the API key. The response
    object is read only for status_code and the x-request-id header — both
    routinely included in support tickets.
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
            except Exception:
                pass

    return {
        "error_type": exc.__class__.__name__,
        "message": _redact_secrets(str(exc))[:_ERROR_MESSAGE_MAX_CHARS],
        "status_code": status_code,
        "request_id": request_id,
    }


def _extract_response_text(response: Any) -> str:
    """Pull text out of an OpenAI Responses API result without assuming SDK version."""
    text = getattr(response, "output_text", None)
    if text:
        return str(text).strip()

    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(str(value))

    return "\n".join(chunks).strip()


def _extract_chat_completion_text(response: Any) -> str:
    """Pull text out of an OpenAI-compatible chat completion result."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""

    first = choices[0]
    message = getattr(first, "message", None)
    if message is None and isinstance(first, dict):
        message = first.get("message")

    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)

    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
            else:
                text = getattr(item, "text", None) or getattr(item, "content", None)
            if text:
                chunks.append(str(text))
        return "\n".join(chunks).strip()

    return str(content or "").strip()


def _base_payload(provider: str, primary_model: str) -> Dict[str, Any]:
    return {
        "provider": provider,
        "provider_available": _provider_key_present(provider),
        "openai_available": _openai_key_present(),
        "deepseek_available": _deepseek_key_present(),
        "ai_model": primary_model,
    }


def _failure_payload(
    last_error: Optional[Dict[str, Any]],
    provider: str,
    primary_model: str,
    fallback_model: str,
) -> Dict[str, Any]:
    payload = {
        "success": False,
        "type": f"{provider}_error_fallback",
        "response_source": "fallback",
        "error": last_error.get("error_type") if last_error else "UnknownAIError",
        "error_detail": last_error,
        "text": _FALLBACK_TEXT,
        "fallback_model": fallback_model,
        **_base_payload(provider, primary_model),
    }
    if provider == "deepseek":
        payload["deepseek_model"] = primary_model
    else:
        payload["openai_model"] = primary_model
    return payload


def _rate_limited_payload(
    last_error: Optional[Dict[str, Any]],
    provider: str,
    primary_model: str,
) -> Dict[str, Any]:
    payload = {
        "success": False,
        "type": f"{provider}_rate_limited",
        "response_source": "rate_limited",
        "provider_state": "rate_limited",
        "error": "RateLimitError",
        "error_detail": last_error,
        "text": _RATE_LIMITED_TEXT,
        **_base_payload(provider, primary_model),
    }
    if provider == "deepseek":
        payload["deepseek_model"] = primary_model
    else:
        payload["openai_model"] = primary_model
    return payload


def _build_client(provider: str):
    from openai import OpenAI

    kwargs: Dict[str, Any] = {}
    api_key = _provider_key(provider)
    if api_key:
        kwargs["api_key"] = api_key
    if provider == "deepseek":
        kwargs["base_url"] = DEEPSEEK_BASE_URL
    # Disable SDK retries for chat requests - handle 429 explicitly instead
    kwargs["max_retries"] = 0
    # Set explicit timeout to prevent 21-second hangs
    kwargs["timeout"] = 15.0
    return OpenAI(**kwargs)


def _call_openai_responses(
    client: Any,
    model: str,
    system_prompt: str,
    final_user_message: str,
    *,
    smoke: bool,
) -> str:
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
    return _extract_response_text(response)


def _call_deepseek_chat(
    client: Any,
    model: str,
    system_prompt: str,
    final_user_message: str,
    *,
    smoke: bool,
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_user_message},
        ],
        max_tokens=(
            _SMOKE_MAX_OUTPUT_TOKENS if smoke else _DEFAULT_MAX_OUTPUT_TOKENS
        ),
    )
    return _extract_chat_completion_text(response)


def call_openai_minimal(
    user_message: str,
    profile_context: Optional[str] = None,
    *,
    smoke: bool = False,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Send the simplest possible call to the active premium provider.

    The function name is preserved for backward compatibility. `provider`
    accepts "openai" or "deepseek"; default is "openai".
    """

    active_provider = _provider_name(provider)
    primary_model, fallback_model = _provider_models(active_provider)
    profile_present = bool(profile_context)

    try:
        client = _build_client(active_provider)
    except Exception as exc:
        last_error = _safe_openai_error(exc)
        logger.warning(
            "Rico AI client init/import failed",
            extra={
                "provider": active_provider,
                "ai_error": last_error,
                "smoke": smoke,
            },
        )
        payload = _failure_payload(last_error, active_provider, primary_model, fallback_model)
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
    model_attempts = [primary_model]
    if fallback_model and fallback_model != primary_model:
        model_attempts.append(fallback_model)

    for model in model_attempts:
        try:
            if active_provider == "deepseek":
                text = _call_deepseek_chat(
                    client,
                    model,
                    system_prompt,
                    final_user_message,
                    smoke=smoke,
                )
            else:
                text = _call_openai_responses(
                    client,
                    model,
                    system_prompt,
                    final_user_message,
                    smoke=smoke,
                )

            if not text:
                raise RuntimeError(f"{active_provider} response returned empty text")

            return {
                "success": True,
                "response_source": active_provider,
                "provider": active_provider,
                "model": model,
                "text": text,
                "profile_context_present": profile_present,
                **_base_payload(active_provider, model),
            }

        except Exception as exc:
            last_error = _safe_openai_error(exc)
            is_rate_limit = (
                last_error.get("status_code") == 429
                or "RateLimitError" in last_error.get("error_type", "")
            )
            logger.warning(
                "Rico AI provider rate limited — skipping retry"
                if is_rate_limit
                else "Rico AI provider call failed safely",
                extra={
                    "provider": active_provider,
                    "ai_error": last_error,
                    "model": model,
                    "smoke": smoke,
                    "profile_context_present": profile_present,
                },
            )
            if is_rate_limit:
                payload = _rate_limited_payload(last_error, active_provider, model)
                payload["profile_context_present"] = profile_present
                payload["is_rate_limited"] = True
                return payload

    payload = _failure_payload(last_error, active_provider, primary_model, fallback_model)
    payload["profile_context_present"] = profile_present
    return payload
