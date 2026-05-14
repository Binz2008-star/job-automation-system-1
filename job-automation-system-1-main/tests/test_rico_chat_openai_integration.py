"""
tests/test_rico_chat_openai_integration.py

Verifies that the open-ended chat fallback in RicoChatAPI delegates to
RicoOpenAIAgent and passes the loaded profile as user_context.

These tests do NOT call OpenAI. They mock the agent boundary to assert the
contract: open-ended message → agent.respond(message, user_context=profile).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Required for any module that imports the API stack at collection time.
os.environ.setdefault("ADMIN_EMAIL", "rico-test@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "ricopass123")
os.environ.setdefault("JWT_SECRET", "ricosecret" + "x" * 21)

_AI_ENV_VARS = [
    "OPENAI_API_KEY",
    "OPEN_AI_API",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_FALLBACK_MODEL",
    "HF_API_TOKEN",
    "HF_TOKEN",
    "HF_API_KEY",
    "HUGGINGFACE_API_KEY",
    "RICO_AI_PROVIDER",
]


@pytest.fixture(autouse=True)
def clear_ai_env():
    saved = {name: os.environ.get(name) for name in _AI_ENV_VARS}
    for name in _AI_ENV_VARS:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture
def chat_api():
    """Build a RicoChatAPI with stubbed dependencies."""
    from src.rico_chat_api import RicoChatAPI

    api = RicoChatAPI()
    # Memory store writes are not under test here — neutralise side effects.
    api.memory = MagicMock()
    return api


def _stub_active_user(monkeypatch, profile):
    """Force _handle_active_user to be entered with a known profile."""
    monkeypatch.setattr("src.rico_chat_api.is_onboarding_complete", lambda _u: True)
    monkeypatch.setattr("src.rico_chat_api.get_profile", lambda _u: profile)


# ── 1. Open-ended chat reaches the OpenAI agent ───────────────────────────────


def test_open_ended_message_calls_openai_agent(chat_api, monkeypatch):
    """A non-keyword user message must be routed to RicoOpenAIAgent.respond()."""
    profile = {
        "user_id": "alice@rico.ai",
        "target_roles": ["Senior HSE Manager"],
        "preferred_cities": ["Dubai"],
    }
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent = MagicMock()
    chat_api.openai_agent.respond.return_value = {
        "type": "openai_response",
        "message": "Profile-aware reply for Alice.",
    }

    result = chat_api._handle_active_user("alice@rico.ai", "tell me about my prospects")

    assert chat_api.openai_agent.respond.called, "OpenAI agent must be invoked for open-ended messages"
    assert result["message"] == "Profile-aware reply for Alice."


# ── 2. Missing OpenAI key → safe fallback (no exception) ──────────────────────


def test_missing_openai_key_returns_safe_fallback(chat_api, monkeypatch):
    """When OPENAI_API_KEY is not configured and no HF key, the agent's built-in fallback fires."""
    profile = {"user_id": "bob@rico.ai", "target_roles": ["HSE Officer"]}
    _stub_active_user(monkeypatch, profile)

    # Simulate: RicoOpenAIAgent with no key. Patch all env var names to be safe.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPEN_AI_API", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)

    from src.rico_openai_agent import RicoOpenAIAgent

    chat_api.openai_agent = RicoOpenAIAgent()
    assert chat_api.openai_agent.available is False, "Agent must report unavailable without key"
    assert chat_api.openai_agent.hf_available is False, "Agent must report no HF without key"

    result = chat_api._handle_active_user("bob@rico.ai", "what's the next step?")

    assert "message" in result, "Fallback must still return a 'message' field"
    assert result["message"], "Fallback message must not be empty"
    assert result["type"] == "fallback_response"
    assert result.get("provider") == "fallback"


# ── 3. Profile context is passed into the OpenAI agent ────────────────────────


def test_profile_context_passed_to_openai_agent(chat_api, monkeypatch):
    """The loaded profile must be forwarded as user_context to respond()."""
    profile = {
        "user_id": "carol@rico.ai",
        "name": "Carol",
        "target_roles": ["QHSE Manager"],
        "preferred_cities": ["Abu Dhabi"],
        "skills": ["NEBOSH", "ISO 45001"],
        "salary_expectation_aed": 35000,
    }
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent = MagicMock()
    chat_api.openai_agent.respond.return_value = {"type": "openai_response", "message": "ok"}

    chat_api._handle_active_user("carol@rico.ai", "advise me")

    args, kwargs = chat_api.openai_agent.respond.call_args
    forwarded_context = kwargs.get("user_context") or (args[1] if len(args) > 1 else None)

    assert forwarded_context is not None, "user_context must be passed to respond()"
    assert forwarded_context["profile_exists"] is True
    assert forwarded_context["target_roles"] == ["QHSE Manager"]
    assert forwarded_context["preferred_cities"] == ["Abu Dhabi"]
    assert forwarded_context["skills"] == ["NEBOSH", "ISO 45001"]
    assert forwarded_context["salary_expectation_aed"] == 35000
    # Empty fields must be dropped to keep the prompt tight.
    assert "phone" not in forwarded_context


# ── 4. Env var compatibility shim — OPEN_AI_API legacy fallback ───────────────


def test_legacy_env_var_is_recognized(monkeypatch):
    """When only OPEN_AI_API is set, the agent should still report available."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_AI_API", "sk-legacy-test-value")

    from src.rico_openai_agent import RicoOpenAIAgent

    agent = RicoOpenAIAgent()
    assert agent.available is True, "Agent must accept OPEN_AI_API as a fallback name"
