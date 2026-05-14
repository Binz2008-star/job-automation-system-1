"""
tests/test_onboarding_state.py
Tests for server-side onboarding state persistence (Issue #23).

All DB calls are patched — no real database required.
Invariants verified:
  - completed users never see the onboarding welcome prompt again
  - "what's next?" always returns job-search options for completed users
  - state transitions: None → pending/in_progress → completed
  - DB unavailable degrades gracefully (JSON profile fallback)
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models.onboarding import (
    ONBOARDING_COMPLETED,
    ONBOARDING_IN_PROGRESS,
    ONBOARDING_PENDING,
    OnboardingState,
)
from src.rico_agent import RicoProfile


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _state(status: str, user_id: str = "u1") -> OnboardingState:
    return OnboardingState(user_id=user_id, status=status)


def _make_api():
    from src.rico_chat_api import RicoChatAPI
    api = RicoChatAPI.__new__(RicoChatAPI)
    api.memory = MagicMock()
    api.agent  = MagicMock()
    api.system = MagicMock()
    api.memory.load_profile.return_value = MagicMock()   # profile exists by default
    api.system.run_for_profile.return_value = {"matches": []}
    return api


# ── OnboardingState model ─────────────────────────────────────────────────────

class TestOnboardingStateModel:
    def test_completed_is_complete(self):
        assert _state(ONBOARDING_COMPLETED).is_complete() is True

    def test_in_progress_not_complete(self):
        assert _state(ONBOARDING_IN_PROGRESS).is_complete() is False

    def test_pending_not_complete(self):
        assert _state(ONBOARDING_PENDING).is_complete() is False


# ── onboarding_repo unit tests ────────────────────────────────────────────────

class TestOnboardingRepo:
    def test_get_returns_none_when_db_unavailable(self):
        from src.repositories.onboarding_repo import get_onboarding_state
        with patch("src.db.is_db_available", return_value=False):
            result = get_onboarding_state("u1")
        assert result is None

    def test_get_returns_none_when_no_connection(self):
        from src.repositories.onboarding_repo import get_onboarding_state
        with patch("src.db.is_db_available", return_value=True), \
             patch("src.db.get_db_connection", return_value=None):
            result = get_onboarding_state("u1")
        assert result is None

    def test_get_returns_none_when_row_absent(self):
        from src.repositories.onboarding_repo import get_onboarding_state
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        with patch("src.db.is_db_available", return_value=True), \
             patch("src.db.get_db_connection", return_value=conn):
            result = get_onboarding_state("u1")
        assert result is None

    def test_get_returns_state_when_row_present(self):
        from src.repositories.onboarding_repo import get_onboarding_state
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            ONBOARDING_COMPLETED, None, None
        )
        with patch("src.db.is_db_available", return_value=True), \
             patch("src.db.get_db_connection", return_value=conn):
            result = get_onboarding_state("u1")
        assert result is not None
        assert result.status == ONBOARDING_COMPLETED
        assert result.is_complete() is True

    def test_is_onboarding_complete_true(self):
        from src.repositories.onboarding_repo import is_onboarding_complete
        with patch("src.repositories.onboarding_repo.get_onboarding_state",
                   return_value=_state(ONBOARDING_COMPLETED)):
            assert is_onboarding_complete("u1") is True

    def test_is_onboarding_complete_false_in_progress(self):
        from src.repositories.onboarding_repo import is_onboarding_complete
        with patch("src.repositories.onboarding_repo.get_onboarding_state",
                   return_value=_state(ONBOARDING_IN_PROGRESS)):
            assert is_onboarding_complete("u1") is False

    def test_is_onboarding_complete_false_db_unavailable(self):
        from src.repositories.onboarding_repo import is_onboarding_complete
        with patch("src.repositories.onboarding_repo.get_onboarding_state", return_value=None):
            assert is_onboarding_complete("u1") is False

    def test_set_status_silently_skips_when_db_unavailable(self):
        from src.repositories.onboarding_repo import set_onboarding_status
        with patch("src.db.is_db_available", return_value=False):
            set_onboarding_status("u1", ONBOARDING_COMPLETED)   # must not raise

    def test_mark_complete_calls_set_with_completed(self):
        from src.repositories.onboarding_repo import mark_onboarding_complete
        with patch("src.repositories.onboarding_repo.set_onboarding_status") as mock_set:
            mark_onboarding_complete("u1")
        mock_set.assert_called_once_with("u1", ONBOARDING_COMPLETED)


# ── process_message: first-time onboarding ───────────────────────────────────

class TestFirstTimeOnboarding:
    def test_new_user_gets_onboarding_welcome(self):
        api = _make_api()
        with patch("src.rico_chat_api.is_onboarding_complete", return_value=False), \
             patch("src.rico_chat_api.get_profile", return_value=None), \
             patch("src.rico_chat_api.upsert_profile", return_value=MagicMock()), \
             patch("src.rico_chat_api.set_onboarding_status") as mock_set, \
             patch("src.rico_chat_api.mark_onboarding_complete"):
            response = api.process_message("new-user", "hello")
        assert response["type"] == "onboarding"
        assert "Welcome to Rico AI" in response["message"]
        mock_set.assert_called_once_with("new-user", ONBOARDING_IN_PROGRESS)

    def test_onboarding_welcome_not_shown_when_state_is_completed(self):
        """Core regression: completed users must never see onboarding again."""
        api = _make_api()
        api.memory.load_profile.return_value = None  # even if profile is gone
        with patch("src.rico_chat_api.is_onboarding_complete", return_value=True), \
             patch("src.rico_chat_api.mark_onboarding_complete"):
            response = api.process_message("done-user", "hello")
        assert response["type"] != "onboarding"

    def test_second_message_marks_onboarding_complete(self):
        """After the welcome, any message from user with existing profile → complete."""
        api = _make_api()
        with patch("src.rico_chat_api.is_onboarding_complete", return_value=False), \
             patch("src.rico_chat_api.get_profile", return_value=RicoProfile(user_id="u1")), \
             patch("src.rico_chat_api.mark_onboarding_complete") as mock_complete:
            api.process_message("u1", "find me jobs")
        mock_complete.assert_called_once_with("u1")

    def test_cv_upload_marks_complete_and_skips_onboarding(self):
        api = _make_api()
        with patch("src.rico_chat_api.is_onboarding_complete", return_value=False), \
             patch("src.rico_chat_api.upsert_profile", return_value=RicoProfile(user_id="cv-user")), \
             patch("src.rico_chat_api.mark_onboarding_complete") as mock_complete:
            response = api.process_message("cv-user", "my cv is Roben_Edwan_CV.pdf")
        assert response["type"] == "cv_first_profile"
        mock_complete.assert_called_once_with("cv-user")


# ── process_message: completed users ─────────────────────────────────────────

class TestCompletedUserRouting:
    def _completed(self, message: str, user_id: str = "done-user") -> dict:
        api = _make_api()
        with patch("src.rico_chat_api.is_onboarding_complete", return_value=True), \
             patch("src.rico_chat_api.mark_onboarding_complete"):
            return api.process_message(user_id, message)

    def test_whats_next_returns_options(self):
        r = self._completed("what's next?")
        assert r["type"] == "options"
        assert "options" in r
        assert len(r["options"]) >= 4

    def test_whats_next_variants(self):
        for phrase in ["whats next", "what now", "help", "options", "menu", "next steps"]:
            r = self._completed(phrase)
            assert r["type"] == "options", f"Expected options for phrase: {phrase!r}"

    def test_find_jobs_returns_job_matches(self):
        r = self._completed("find jobs for me")
        assert r["type"] == "job_matches"

    def test_apply_returns_application(self):
        r = self._completed("I want to apply")
        assert r["type"] == "confirmation_required"
        assert r["intent"] == "apply_job"

    def test_interview_returns_interview_prep(self):
        r = self._completed("prepare me for interview")
        assert r["type"] == "interview_prep"

    def test_generic_message_returns_assistant(self):
        r = self._completed("can you explain something")
        assert r["type"] == "fallback_response"
        assert "message" in r

    def test_completed_user_never_gets_onboarding_type(self):
        for msg in ["hello", "hi", "what's next", "start", "begin", "welcome"]:
            r = self._completed(msg)
            assert r["type"] != "onboarding", f"Got onboarding for completed user msg: {msg!r}"


# ── DB graceful degradation ───────────────────────────────────────────────────

class TestGracefulDegradation:
    def test_db_down_new_user_still_gets_onboarding(self):
        """When DB is unavailable, fall back to profile existence check."""
        api = _make_api()
        with patch("src.rico_chat_api.is_onboarding_complete", return_value=False), \
             patch("src.rico_chat_api.get_profile", return_value=None), \
             patch("src.rico_chat_api.upsert_profile", return_value=MagicMock()), \
             patch("src.rico_chat_api.set_onboarding_status"), \
             patch("src.rico_chat_api.mark_onboarding_complete"):
            response = api.process_message("offline-user", "hi")
        assert response["type"] == "onboarding"

    def test_db_down_existing_profile_user_gets_active_response(self):
        """User with existing profile gets active response even if DB is down."""
        api = _make_api()
        with patch("src.rico_chat_api.is_onboarding_complete", return_value=False), \
             patch("src.rico_chat_api.get_profile", return_value=RicoProfile(user_id="existing-user")), \
             patch("src.rico_chat_api.set_onboarding_status"), \
             patch("src.rico_chat_api.mark_onboarding_complete"):
            response = api.process_message("existing-user", "find jobs")
        assert response["type"] != "onboarding"
