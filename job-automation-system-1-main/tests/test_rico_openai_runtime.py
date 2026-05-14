"""
tests/test_rico_openai_runtime.py

Covers the minimal Rico OpenAI runtime helper and the chat/smoke surfaces
that depend on it. None of these tests perform real OpenAI network calls;
the OpenAI client is replaced with a stub at the module boundary
(``openai.OpenAI``) so we exercise the helper's branching logic.

What this file proves:

  1. Smoke endpoint: returns the structured success shape on a successful
     helper call.
  2. Chat: returns OpenAI text + ``response_source=openai`` on a successful
     helper call.
  3. Chat: preserves the fallback shape (``response_source=fallback``,
     ``type=openai_error_fallback``, ``error``, ``error_detail``,
     ``fallback_model``) when the helper fails for both models.
  4. Error/log path never carries the API key or full profile contents.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
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


# ── Test doubles ──────────────────────────────────────────────────────────────


class _FakeOpenAIError(Exception):
    """Mimics openai SDK exception shape: status_code, request_id, response."""

    def __init__(self, message="500 InternalServerError", *, status_code=500, request_id="req_test"):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.response = SimpleNamespace(
            status_code=status_code,
            headers={"x-request-id": request_id},
        )


class _FakeOpenAIClient:
    """Stand-in for openai.OpenAI() that returns the configured response."""

    def __init__(self, *, output_text=None, raise_on_call=None):
        self._output_text = output_text
        self._raise = raise_on_call
        self.responses = self
        self.chat = SimpleNamespace(completions=self)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self._raise is not None:
            raise self._raise
        if "messages" in kwargs:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=self._output_text)
                    )
                ]
            )
        return SimpleNamespace(output_text=self._output_text, output=[])


def _patch_openai(monkeypatch, client):
    """Patch the OpenAI SDK import inside rico_openai_runtime."""
    import openai

    monkeypatch.setattr(openai, "OpenAI", lambda *a, **kw: client, raising=False)


# ── 1. Helper success/failure unit tests ─────────────────────────────────────


def test_helper_success_returns_structured_payload(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test")
    client = _FakeOpenAIClient(output_text="Hello from Rico.")
    _patch_openai(monkeypatch, client)

    from src.rico_openai_runtime import call_openai_minimal

    result = call_openai_minimal("hi there", profile_context="role: HSE Manager")

    assert result["success"] is True
    assert result["response_source"] == "openai"
    assert result["text"] == "Hello from Rico."
    assert result["openai_available"] is True
    assert result["profile_context_present"] is True
    # Primary model is what the helper attempted first.
    assert result["model"]
    # Profile context must have been included in the prompt — but not the
    # API key.
    sent = client.calls[0]["input"]
    user_msg = next(m for m in sent if m["role"] == "user")["content"]
    assert "HSE Manager" in user_msg
    assert "sk-fake-test" not in user_msg


def test_helper_deepseek_success_returns_structured_payload(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dsk-fake-test")
    client = _FakeOpenAIClient(output_text="Hello from DeepSeek.")
    _patch_openai(monkeypatch, client)

    from src.rico_openai_runtime import call_openai_minimal

    result = call_openai_minimal(
        "hi there",
        profile_context="role: HSE Manager",
        provider="deepseek",
    )

    assert result["success"] is True
    assert result["response_source"] == "deepseek"
    assert result["provider"] == "deepseek"
    assert result["deepseek_available"] is True
    assert result["provider_available"] is True
    assert result["text"] == "Hello from DeepSeek."
    sent = client.calls[0]
    assert sent["model"]
    assert "messages" in sent
    user_msg = next(m for m in sent["messages"] if m["role"] == "user")["content"]
    assert "HSE Manager" in user_msg


def test_helper_failure_returns_safe_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test")
    err = _FakeOpenAIError("500 InternalServerError")
    client = _FakeOpenAIClient(raise_on_call=err)
    _patch_openai(monkeypatch, client)

    from src.rico_openai_runtime import (
        OPENAI_FALLBACK_MODEL,
        OPENAI_PRIMARY_MODEL,
        call_openai_minimal,
    )

    result = call_openai_minimal("hi", profile_context=None)

    assert result["success"] is False
    assert result["type"] == "openai_error_fallback"
    assert result["response_source"] == "fallback"
    assert result["openai_available"] is True
    assert result["openai_model"] == OPENAI_PRIMARY_MODEL
    assert result["fallback_model"] == OPENAI_FALLBACK_MODEL
    assert result["error"] == "_FakeOpenAIError"
    assert result["error_detail"]["status_code"] == 500
    assert result["error_detail"]["request_id"] == "req_test"
    assert result["text"]  # safe templated reply must be non-empty
    # Tried both primary and fallback models before giving up.
    assert len(client.calls) == 2


def test_helper_smoke_truncates_input_and_caps_tokens(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test")
    client = _FakeOpenAIClient(output_text="OK")
    _patch_openai(monkeypatch, client)

    from src.rico_openai_runtime import call_openai_minimal

    long_profile = "X" * 5000  # would exceed 1200-char cap if not truncated
    result = call_openai_minimal("ignored when smoke=True", profile_context=long_profile, smoke=True)

    assert result["success"] is True
    sent = client.calls[0]
    assert sent["max_output_tokens"] == 80
    user_msg = next(m for m in sent["input"] if m["role"] == "user")["content"]
    # Smoke input is the literal probe — profile context is not included.
    assert user_msg == "Say OK"


def test_helper_truncates_profile_context_to_1200_chars(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test")
    client = _FakeOpenAIClient(output_text="ok")
    _patch_openai(monkeypatch, client)

    from src.rico_openai_runtime import call_openai_minimal

    long_profile = "Y" * 5000
    call_openai_minimal("question", profile_context=long_profile)
    user_msg = next(m for m in client.calls[0]["input"] if m["role"] == "user")["content"]
    # Only 1200 Y's should appear, never the full 5000.
    assert user_msg.count("Y") == 1200


def test_helper_error_detail_truncates_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test")
    huge = "Z" * 2000
    err = _FakeOpenAIError(huge, status_code=503)
    client = _FakeOpenAIClient(raise_on_call=err)
    _patch_openai(monkeypatch, client)

    from src.rico_openai_runtime import call_openai_minimal

    result = call_openai_minimal("hi")
    assert len(result["error_detail"]["message"]) <= 500


def test_helper_no_key_returns_fallback_without_calling_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPEN_AI_API", raising=False)

    # Patch OpenAI() so it raises like the SDK does when the key is missing.
    def _raise_on_init(*a, **kw):
        raise _FakeOpenAIError("OpenAI API key not configured", status_code=None, request_id=None)

    import openai
    monkeypatch.setattr(openai, "OpenAI", _raise_on_init, raising=False)

    from src.rico_openai_runtime import call_openai_minimal

    result = call_openai_minimal("hi")
    assert result["success"] is False
    assert result["type"] == "openai_error_fallback"
    assert result["openai_available"] is False
    assert result["error"] == "_FakeOpenAIError"


def test_helper_no_deepseek_key_returns_fallback(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def _raise_on_init(*a, **kw):
        raise _FakeOpenAIError("DeepSeek API key not configured", status_code=None, request_id=None)

    import openai
    monkeypatch.setattr(openai, "OpenAI", _raise_on_init, raising=False)

    from src.rico_openai_runtime import call_openai_minimal

    result = call_openai_minimal("hi", provider="deepseek")
    assert result["success"] is False
    assert result["type"] == "deepseek_error_fallback"
    assert result["deepseek_available"] is False


# ── 2. Smoke endpoint integration ────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.api.app import app
    return TestClient(app, raise_server_exceptions=False)


def _authenticate(client):
    """Mint a JWT and attach it as the access_token cookie.

    Faster and more deterministic than POSTing to /api/v1/auth/login, which
    needs a matching DB user. Mirrors the pattern used elsewhere in the suite.
    """
    from src.api.auth import create_access_token
    token = create_access_token({"sub": "smoke-test@rico.ai", "role": "user"})
    client.cookies.set("access_token", token)


def test_smoke_endpoint_returns_success_shape_when_helper_succeeds(client):
    _authenticate(client)
    fake_result = {
        "success": True,
        "response_source": "openai",
        "model": "gpt-4o-mini",
        "text": "OK",
        "openai_available": True,
        "profile_context_present": False,
    }
    with patch("src.rico_env.get_ai_provider", return_value="openai"), \
         patch("src.rico_openai_runtime.call_openai_minimal", return_value=fake_result):
        r = client.get("/api/v1/rico/openai-smoke")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["model"] == "gpt-4o-mini"
    assert body["response"] == "OK"
    assert body["error"] is None
    assert body["openai_available"] is True


def test_smoke_endpoint_returns_failure_shape_when_helper_fails(client):
    _authenticate(client)
    fake_result = {
        "success": False,
        "type": "openai_error_fallback",
        "response_source": "fallback",
        "openai_available": True,
        "openai_model": "gpt-4o-mini",
        "fallback_model": "gpt-4.1-mini",
        "profile_context_present": False,
        "error": "InternalServerError",
        "error_detail": {
            "error_type": "InternalServerError",
            "message": "500 server error",
            "status_code": 500,
            "request_id": "req_abc",
        },
        "text": "I understood. I can still help while the AI reasoning layer is being configured.",
    }
    with patch("src.rico_env.get_ai_provider", return_value="openai"), \
         patch("src.rico_openai_runtime.call_openai_minimal", return_value=fake_result):
        r = client.get("/api/v1/rico/openai-smoke")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert body["error"] == "InternalServerError"
    assert body["error_detail"]["status_code"] == 500
    assert body["error_detail"]["request_id"] == "req_abc"
    assert body["fallback_model"] == "gpt-4.1-mini"
    assert body["model"] == "gpt-4o-mini"


def test_smoke_endpoint_requires_auth(client):
    # Drop any cookie a prior test may have set.
    client.cookies.clear()
    r = client.get("/api/v1/rico/openai-smoke")
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


# ── 3. Chat surface contract ─────────────────────────────────────────────────


def _stub_active_user(monkeypatch, profile):
    monkeypatch.setattr("src.rico_chat_api.is_onboarding_complete", lambda _u: True)
    monkeypatch.setattr("src.rico_chat_api.get_profile", lambda _u: profile)


@pytest.fixture
def chat_api():
    from src.rico_chat_api import RicoChatAPI

    api = RicoChatAPI()
    api.memory = MagicMock()
    return api


def test_chat_returns_openai_text_when_helper_succeeds(chat_api, monkeypatch):
    profile = {"user_id": "alice@rico.ai", "target_roles": ["HSE Manager"]}
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent.api_key = "sk-fake-test"
    fake_result = {
        "success": True,
        "response_source": "openai",
        "model": "gpt-4o-mini",
        "text": "I read your profile. Here's a tailored next step.",
        "openai_available": True,
        "profile_context_present": True,
    }
    with patch.dict(os.environ, {"RICO_AI_PROVIDER": "openai"}), \
         patch("src.rico_openai_agent.call_openai_minimal", return_value=fake_result):
        result = chat_api._handle_active_user("alice@rico.ai", "tell me about my prospects")

    assert result["type"] == "openai_response"
    assert result["message"] == "I read your profile. Here's a tailored next step."
    assert result["response_source"] == "openai"
    assert result["openai_available"] is True
    assert result["profile_context_present"] is True


def test_chat_preserves_fallback_shape_when_helper_fails(chat_api, monkeypatch):
    profile = {"user_id": "bob@rico.ai", "target_roles": ["QHSE Manager"]}
    _stub_active_user(monkeypatch, profile)

    chat_api.openai_agent.api_key = "sk-fake-test"
    fake_result = {
        "success": False,
        "type": "openai_error_fallback",
        "response_source": "fallback",
        "openai_available": True,
        "openai_model": "gpt-4o-mini",
        "fallback_model": "gpt-4.1-mini",
        "profile_context_present": True,
        "error": "InternalServerError",
        "error_detail": {
            "error_type": "InternalServerError",
            "message": "500 server error",
            "status_code": 500,
            "request_id": "req_abc",
        },
        "text": "I understood. I can still help while the AI reasoning layer is being configured.",
    }
    with patch.dict(os.environ, {"RICO_AI_PROVIDER": "openai"}), \
         patch("src.rico_openai_agent.call_openai_minimal", return_value=fake_result):
        result = chat_api._handle_active_user("bob@rico.ai", "what should I do next?")

    # Fallback shape preserved.
    assert result["type"] == "openai_error_fallback"
    assert result["response_source"] == "fallback"
    assert result["error"] == "InternalServerError"
    assert result["error_detail"]["status_code"] == 500
    assert result["error_detail"]["request_id"] == "req_abc"
    assert result["fallback_model"] == "gpt-4.1-mini"
    assert result["openai_available"] is True
    assert result["profile_context_present"] is True


# ── 4. Secret / profile leakage ──────────────────────────────────────────────


def test_helper_failure_payload_does_not_contain_api_key_or_profile(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-MUST-NEVER-LEAK")
    err = _FakeOpenAIError("auth: sk-MUST-NEVER-LEAK is not valid")
    client = _FakeOpenAIClient(raise_on_call=err)
    _patch_openai(monkeypatch, client)

    from src.rico_openai_runtime import call_openai_minimal

    profile = "phone=+971500000000; salary_expectation_aed=35000; skills=NEBOSH,ISO45001"
    result = call_openai_minimal("hi", profile_context=profile)

    serialized = repr(result)
    assert "sk-MUST-NEVER-LEAK" not in serialized
    # The profile context was passed in, but failure payload must not echo it.
    assert "+971500000000" not in serialized
    assert "salary_expectation_aed" not in serialized
    assert "NEBOSH" not in serialized
