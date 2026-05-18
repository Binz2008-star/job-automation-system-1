"""
tests/test_rico_hf_router.py

Tests for:
  - rico_intent_router: routing, entity extraction, confirmation gate
  - rico_hf_client: graceful fallback when HF is unavailable
  - rico_openai_agent: HF-primary mode, OpenAI disabled by default
  - Jotform onboarding flow (chat_service path)
"""
from __future__ import annotations

import os
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


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


# ── Intent router tests ───────────────────────────────────────────────────────

class TestIntentRouter:
    """Rico works with no OPENAI_API_KEY. All routing is deterministic."""

    def _route(self, msg: str, context: Dict[str, Any] | None = None):
        from src.rico_intent_router import route
        return route(msg, user_id="test-user", context=context)

    def test_search_jobs_marketing_dubai(self):
        result = self._route("Find Marketing Manager jobs in Dubai above 18k")
        assert result.intent == "search_jobs"
        assert result.tool_name == "search_jobs"
        assert result.entities.get("city") == "Dubai"
        assert result.confidence >= 0.80

    def test_search_jobs_generic(self):
        result = self._route("Show me HSE Manager roles in Abu Dhabi")
        assert result.intent == "search_jobs"
        assert result.entities.get("city") == "Abu Dhabi"

    def test_save_first_job(self):
        result = self._route("save the first one")
        assert result.intent == "save_job"
        assert result.entities.get("job_index") == 0

    def test_save_second_job(self):
        result = self._route("save the second one")
        assert result.intent == "save_job"
        assert result.entities.get("job_index") == 1

    def test_skip_job(self):
        result = self._route("skip this one, not relevant")
        assert result.intent == "skip_job"

    def test_apply_requires_confirmation(self):
        result = self._route("apply to this")
        assert result.intent == "apply_job"
        assert result.requires_confirmation is True
        assert len(result.confirmation_prompt) > 0

    def test_apply_not_silently_executed(self):
        result = self._route("apply to this")
        # tool_args must NOT have user_has_approved=True
        assert result.tool_args.get("user_has_approved") is False

    def test_draft_cover_letter(self):
        result = self._route("draft a cover letter for this job")
        assert result.intent == "draft_message"

    def test_explain_match(self):
        result = self._route("why did Rico recommend this job?")
        assert result.intent == "explain_match"

    def test_interview_prep(self):
        result = self._route("help me prepare for an interview")
        assert result.intent == "prepare_interview"

    def test_update_preferences_salary(self):
        result = self._route("change my salary expectation to 20k AED")
        assert result.intent == "update_preferences"

    def test_update_preferences_city(self):
        result = self._route("I prefer jobs in Sharjah now")
        assert result.intent == "update_preferences"
        assert result.entities.get("city") == "Sharjah"

    def test_set_reminder(self):
        result = self._route("remind me to follow up on this")
        assert result.intent == "set_reminder"

    def test_help_intent(self):
        result = self._route("help")
        assert result.intent == "help"

    def test_empty_message_returns_unknown(self):
        result = self._route("")
        assert result.intent == "unknown"

    def test_unrelated_message_returns_unknown_or_low_confidence(self):
        result = self._route("what is the weather today?")
        # Either unknown, or at least below 0.90
        if result.intent != "unknown":
            assert result.confidence < 0.90

    def test_years_experience_extracted(self):
        result = self._route("find jobs requiring 5 years experience in Dubai")
        assert result.entities.get("years_experience") == 5

    def test_industry_extracted(self):
        result = self._route("find HSE jobs in Dubai")
        assert result.entities.get("industry") == "hse"

    def test_job_reference_resolved_from_context(self):
        context = {
            "recent_jobs": [
                {"job_key": "abc123", "title": "HSE Manager"},
                {"job_key": "def456", "title": "Safety Lead"},
            ]
        }
        result = self._route("save the second one", context=context)
        assert result.intent == "save_job"
        assert result.tool_args.get("job_key") == "def456"

    def test_no_openai_key_required(self):
        """Router must function entirely without OPENAI_API_KEY."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            result = self._route("Find QA engineer jobs in Dubai")
        assert result.intent in {"search_jobs", "unknown"}


# ── HF client graceful fallback tests ────────────────────────────────────────

class TestHFClientFallback:

    def test_is_available_false_without_token(self):
        from src.rico_hf_client import is_available
        env_patch = {k: "" for k in ["HF_API_TOKEN", "HF_TOKEN", "HF_API_KEY", "HUGGINGFACE_API_KEY"]}
        with patch.dict(os.environ, env_patch):
            assert is_available() is False

    def test_generate_text_returns_none_without_token(self):
        from src.rico_hf_client import generate_text
        env_patch = {k: "" for k in ["HF_API_TOKEN", "HF_TOKEN", "HF_API_KEY", "HUGGINGFACE_API_KEY"]}
        with patch.dict(os.environ, env_patch):
            result = generate_text("hello")
        assert result is None

    def test_classify_intent_returns_none_without_token(self):
        from src.rico_hf_client import classify_intent
        env_patch = {k: "" for k in ["HF_API_TOKEN", "HF_TOKEN", "HF_API_KEY", "HUGGINGFACE_API_KEY"]}
        with patch.dict(os.environ, env_patch):
            result = classify_intent("find jobs", ["search for jobs", "help"])
        assert result is None

    def test_classify_intent_parses_router_array_response(self):
        from src.rico_hf_client import classify_intent

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = [
            {"label": "help", "score": 0.11},
            {"label": "search for jobs", "score": 0.89},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"HF_API_TOKEN": "fake-token"}):
            with patch("src.rico_hf_client.requests.post", return_value=mock_resp) as post_mock:
                result = classify_intent("find jobs", ["search for jobs", "help"])

        assert result == {
            "labels": ["search for jobs", "help"],
            "scores": [0.89, 0.11],
            "top_label": "search for jobs",
            "top_score": 0.89,
        }
        assert post_mock.call_args.args[0] == (
            "https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli"
        )

    def test_classify_intent_keeps_backward_compat_with_legacy_dict_response(self):
        from src.rico_hf_client import classify_intent

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "labels": ["help", "search for jobs"],
            "scores": [0.11, 0.89],
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"HF_API_TOKEN": "fake-token"}):
            with patch("src.rico_hf_client.requests.post", return_value=mock_resp):
                result = classify_intent("find jobs", ["search for jobs", "help"])

        assert result == {
            "labels": ["search for jobs", "help"],
            "scores": [0.89, 0.11],
            "top_label": "search for jobs",
            "top_score": 0.89,
        }

    def test_generate_text_returns_none_on_hf_error(self):
        from src.rico_hf_client import generate_text
        import requests
        with patch.dict(os.environ, {"HF_API_TOKEN": "fake-token"}):
            with patch("src.rico_hf_client.requests.post", side_effect=requests.ConnectionError("offline")):
                result = generate_text("hello")
        assert result is None

    def test_generate_text_returns_none_on_429(self):
        from src.rico_hf_client import generate_text
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        with patch.dict(os.environ, {"HF_API_TOKEN": "fake-token"}):
            with patch("src.rico_hf_client.requests.post", return_value=mock_resp):
                result = generate_text("hello")
        assert result is None

    def test_generate_text_returns_text_on_success(self):
        from src.rico_hf_client import generate_text
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = [{"generated_text": "Here are some tips."}]
        mock_resp.raise_for_status = MagicMock()
        with patch.dict(os.environ, {"HF_API_TOKEN": "fake-token"}):
            with patch("src.rico_hf_client.requests.post", return_value=mock_resp) as post_mock:
                result = generate_text("interview tips")
        assert result == "Here are some tips."
        assert post_mock.call_args.args[0] == (
            "https://router.huggingface.co/hf-inference/models/HuggingFaceH4/zephyr-7b-beta"
        )


# ── RicoOpenAIAgent: HF primary, OpenAI disabled by default ──────────────────

class TestRicoAgentHFPrimary:

    def test_hf_is_primary_when_provider_unset(self):
        """With RICO_AI_PROVIDER unset/hf, OpenAI must NOT be called."""
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "hf", "OPENAI_API_KEY": "sk-fake"}):
            from src.rico_openai_agent import RicoOpenAIAgent
            agent = RicoOpenAIAgent()
            assert agent._use_openai is False

    def test_openai_used_only_when_explicitly_set(self):
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "openai", "OPENAI_API_KEY": "sk-fake"}):
            from src.rico_openai_agent import RicoOpenAIAgent
            agent = RicoOpenAIAgent()
            assert agent._use_openai is True

    def test_deepseek_used_only_when_explicitly_set(self):
        with patch.dict(os.environ, {"RICO_AI_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "dsk-fake"}):
            from src.rico_openai_agent import RicoOpenAIAgent
            agent = RicoOpenAIAgent()
            assert agent._use_deepseek is True

    def test_respond_returns_fallback_without_hf_or_openai(self):
        env_clean = {
            "RICO_AI_PROVIDER": "hf",
            **{k: "" for k in ["HF_API_TOKEN", "HF_TOKEN", "HF_API_KEY", "HUGGINGFACE_API_KEY", "OPENAI_API_KEY"]},
        }
        with patch.dict(os.environ, env_clean):
            from src.rico_openai_agent import RicoOpenAIAgent
            agent = RicoOpenAIAgent()
            result = agent.respond("find me jobs")
        assert result["type"] == "fallback_response"
        assert "message" in result
        assert "OpenAI advanced reasoning" not in result["message"]
        assert "configured AI provider" in result["message"]

    def test_respond_uses_hf_when_available(self):
        env = {"RICO_AI_PROVIDER": "hf", "HF_API_TOKEN": "fake-token"}
        with patch.dict(os.environ, env):
            with patch("src.rico_openai_agent.RicoOpenAIAgent._call_hf_free",
                       return_value={"type": "hf_response", "message": "HF says hello", "provider": "huggingface"}):
                from importlib import reload
                import src.rico_openai_agent as mod
                reload(mod)
                agent = mod.RicoOpenAIAgent()
                result = agent.respond("hello")
        assert result.get("provider") in {"huggingface", "fallback"}

    def test_works_without_openai_api_key(self):
        env_clean = {"RICO_AI_PROVIDER": "hf"}
        with patch.dict(os.environ, env_clean):
            os.environ.pop("OPENAI_API_KEY", None)
            from src.rico_openai_agent import RicoOpenAIAgent
            agent = RicoOpenAIAgent()
            assert agent.available is False
            assert agent._use_openai is False


# ── Jotform onboarding: profile creation + Telegram welcome ──────────────────

class TestJotformOnboarding:

    def _make_payload(self, **kwargs) -> Dict[str, Any]:
        base = {
            "email": "test@example.com",
            "telegram_username": "testuser",
            "full_name": "Test User",
            "target_roles": "HSE Manager",
            "preferred_cities": "Dubai",
        }
        base.update(kwargs)
        return base

    def test_onboarding_accepted_with_email(self):
        from src.services.chat_service import handle_jotform_submission
        with patch("src.rico_jotform_webhook.handle_jotform_submission") as mock_handler:
            mock_handler.return_value = {"status": "ok", "user_id": "test@example.com"}
            result = handle_jotform_submission(self._make_payload())
        assert result.get("status") in {"ok", "accepted"}

    def test_onboarding_accepted_without_db(self):
        from src.services.chat_service import handle_jotform_submission
        with patch(
            "src.rico_jotform_webhook.handle_jotform_submission",
            side_effect=Exception("DB unavailable"),
        ):
            result = handle_jotform_submission(self._make_payload())
        assert result.get("status") == "accepted"

    def test_onboarding_skipped_when_no_user_data(self):
        from src.services.chat_service import handle_jotform_submission
        result = handle_jotform_submission({"formID": "261278237812056"})
        assert result.get("status") == "accepted"
        assert "no profile" in result.get("message", "").lower() or "reachable" in result.get("message", "").lower()

    def test_raw_jotform_labels_normalized(self):
        from src.services.chat_service import _normalize_jotform_payload
        raw = {
            "Full Name": "Robin Edwan",
            "Email Address": "robin@example.com",
            "Target Job Titles": "HSE Manager",
            "Preferred Cities": "Dubai",
        }
        normalized = _normalize_jotform_payload(raw)
        assert normalized["full_name"] == "Robin Edwan"
        assert normalized["email"] == "robin@example.com"
        assert normalized["target_roles"] == "HSE Manager"
        assert normalized["preferred_cities"] == "Dubai"
