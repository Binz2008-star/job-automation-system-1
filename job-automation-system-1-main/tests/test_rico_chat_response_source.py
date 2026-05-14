"""
tests/test_rico_chat_response_source.py

Verifies that /api/v1/rico/chat responses carry the diagnostic metadata
needed to tell, from the wire alone, which code path produced the reply.

Sources:
  * keyword      — deterministic regex-driven branches
  * openai       — successful RicoOpenAIAgent.respond() call against the API
  * huggingface  — HF fallback response
  * rate_limited — OpenAI provider returned 429
  * fallback     — agent reachable but no key, OpenAI exception, or safety refusal

No secrets, no profile contents, no user message bytes are ever asserted
on the response — only flat sanitised metadata fields.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
    from src.rico_chat_api import RicoChatAPI

    api = RicoChatAPI()
    api.memory = MagicMock()
    return api


def _stub_active_user(monkeypatch, profile):
    monkeypatch.setattr("src.rico_chat_api.is_onboarding_complete", lambda _u: True)
    monkeypatch.setattr("src.rico_chat_api.get_profile", lambda _u: profile)


def _assert_metadata(resp, *, source, openai_available, profile_present, hf_available=None):
    """Common shape check: every chat reply must carry the diagnostic fields."""
    assert resp["response_source"] == source, (
        f"expected response_source={source!r}, got {resp.get('response_source')!r}"
    )
    assert resp["openai_available"] is openai_available
    assert resp["profile_context_present"] is profile_present
    if hf_available is not None:
        assert resp["hf_available"] is hf_available
    # Model name is informational only; never the key.
    assert isinstance(resp["openai_model"], str) and resp["openai_model"]
    assert "sk-" not in resp["openai_model"], "model field must never carry a key prefix"


# ── 1. Deterministic keyword branch → response_source = "keyword" ─────────────


def test_keyword_branch_reports_keyword_source(chat_api, monkeypatch):
    """A 'find jobs' message must report response_source=keyword and never reach OpenAI."""
    profile = {"user_id": "alice@rico.ai", "target_roles": ["HSE Manager"]}
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent = MagicMock()
    chat_api.openai_agent.available = True
    chat_api.openai_agent.model = "gpt-4.1-mini"
    chat_api.system = MagicMock()
    chat_api.system.run_for_profile.return_value = {"matches": []}

    resp = chat_api._handle_active_user("alice@rico.ai", "find jobs for me")

    _assert_metadata(resp, source="keyword", openai_available=True, profile_present=True)
    assert resp["type"] == "job_matches"
    chat_api.openai_agent.respond.assert_not_called(), "keyword branch must short-circuit before OpenAI"


# ── 2. OpenAI agent succeeds → response_source = "openai" ─────────────────────


def test_openai_branch_reports_openai_source(chat_api, monkeypatch):
    """A non-keyword message routed through a mocked-available agent must report openai."""
    profile = {"user_id": "bob@rico.ai", "target_roles": ["QHSE Manager"]}
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent = MagicMock()
    chat_api.openai_agent.available = True
    chat_api.openai_agent.model = "gpt-4.1-mini"
    chat_api.openai_agent.respond.return_value = {
        "type": "openai_response",
        "message": "Profile-aware reply.",
        "model": "gpt-4.1-mini",
    }

    resp = chat_api._handle_active_user("bob@rico.ai", "what should I do next?")

    _assert_metadata(resp, source="openai", openai_available=True, profile_present=True)
    assert chat_api.openai_agent.respond.called


def test_deepseek_branch_reports_deepseek_source(chat_api, monkeypatch):
    """A DeepSeek-backed reply must report response_source=deepseek."""
    profile = {"user_id": "deepseek@rico.ai", "target_roles": ["Operations Manager"]}
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent = MagicMock()
    chat_api.openai_agent.available = True
    chat_api.openai_agent.openai_available = False
    chat_api.openai_agent.deepseek_available = True
    chat_api.openai_agent.provider_available = True
    chat_api.openai_agent.model = "deepseek-v4-flash"
    chat_api.openai_agent.respond.return_value = {
        "type": "deepseek_response",
        "message": "DeepSeek-powered reply.",
        "model": "deepseek-v4-flash",
        "provider": "deepseek",
    }

    resp = chat_api._handle_active_user("deepseek@rico.ai", "what should I do next?")

    _assert_metadata(resp, source="deepseek", openai_available=False, profile_present=True)
    assert resp["provider"] == "deepseek"
    assert resp["deepseek_available"] is True


# ── 3. Missing key → response_source = "fallback" ─────────────────────────────


def test_missing_key_reports_fallback_source(chat_api, monkeypatch):
    """With OPENAI_API_KEY unset and no HF key the real agent's templated fallback must report fallback."""
    profile = {"user_id": "carol@rico.ai", "target_roles": ["HSE Officer"]}
    _stub_active_user(monkeypatch, profile)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPEN_AI_API", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)

    from src.rico_openai_agent import RicoOpenAIAgent

    chat_api.openai_agent = RicoOpenAIAgent()
    assert chat_api.openai_agent.available is False
    assert chat_api.openai_agent.hf_available is False

    resp = chat_api._handle_active_user("carol@rico.ai", "tell me about the market")

    _assert_metadata(resp, source="fallback", openai_available=False, profile_present=True, hf_available=False)
    assert resp["type"] == "fallback_response"


# ── 4. Greetings ("hi") fall through to OpenAI, not to a hidden keyword ───────


def test_greeting_falls_through_to_openai_path(chat_api, monkeypatch):
    """A bare 'hi' must not match any keyword — it must reach RicoOpenAIAgent.respond()."""
    profile = {"user_id": "dave@rico.ai"}
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent = MagicMock()
    chat_api.openai_agent.available = True
    chat_api.openai_agent.model = "gpt-4.1-mini"
    chat_api.openai_agent.respond.return_value = {
        "type": "openai_response",
        "message": "Hi Dave, how can I help with your UAE job search?",
    }

    resp = chat_api._handle_active_user("dave@rico.ai", "hi")

    chat_api.openai_agent.respond.assert_called_once()
    _assert_metadata(resp, source="openai", openai_available=True, profile_present=True)


# ── 5. OpenAI 429 → response_source = "rate_limited" ─────────────────────────


def test_openai_rate_limit_reports_rate_limited_source(chat_api, monkeypatch):
    """A mocked OpenAI 429 response must not be collapsed into generic fallback."""
    profile = {"user_id": "erin@rico.ai", "target_roles": ["Operations Manager"]}
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent = MagicMock()
    chat_api.openai_agent.available = True
    chat_api.openai_agent.hf_available = False
    chat_api.openai_agent.model = "gpt-4.1-mini"
    chat_api.openai_agent.respond.return_value = {
        "type": "openai_rate_limited",
        "message": "Rico's AI provider is currently rate-limited.",
        "provider": "openai",
        "provider_state": "rate_limited",
        "response_source": "rate_limited",
    }

    resp = chat_api._handle_active_user("erin@rico.ai", "hi")

    chat_api.openai_agent.respond.assert_called_once()
    _assert_metadata(resp, source="rate_limited", openai_available=True, profile_present=True, hf_available=False)
    assert resp["type"] == "openai_rate_limited"
    assert resp["provider"] == "openai"
    assert resp["provider_state"] == "rate_limited"


# ── 6. Metadata never leaks the OpenAI key or full profile contents ───────────


def test_metadata_does_not_leak_secrets_or_profile(chat_api, monkeypatch):
    """Diagnostic fields must not contain the API key or arbitrary profile fields."""
    profile = {
        "user_id": "eve@rico.ai",
        "skills": ["NEBOSH"],
        "salary_expectation_aed": 35000,
        "phone": "+971500000000",
    }
    _stub_active_user(monkeypatch, profile)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-leak-into-response")

    chat_api.openai_agent = MagicMock()
    chat_api.openai_agent.available = True
    chat_api.openai_agent.model = "gpt-4.1-mini"
    chat_api.openai_agent.respond.return_value = {
        "type": "openai_response",
        "message": "ok",
    }

    resp = chat_api._handle_active_user("eve@rico.ai", "advise me")

    serialized = repr(resp)
    assert "sk-should-never-leak-into-response" not in serialized
    assert "+971500000000" not in serialized
    assert "NEBOSH" not in serialized
    assert "salary_expectation_aed" not in serialized
    # Allowed sanitised fields only.
    assert set(resp.keys()) >= {
        "response_source",
        "openai_available",
        "openai_model",
        "profile_context_present",
    }
