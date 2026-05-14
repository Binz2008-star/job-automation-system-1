"""
tests/test_user_profiles.py
Tests for DB-backed user profiles, preferences, and saved searches (feat/user-profiles).

All DB calls are patched — no real database required.
Invariants verified:
  - get_profile: DB first, JSON fallback when DB unavailable or returns None
  - upsert_profile: writes to DB and JSON mirror; graceful on DB failure
  - get_preferences: DB first, JSON settings fallback
  - save_preferences: upserts via DB; silent when DB unavailable
  - save_search / list_saved_searches: DB-backed, silent fallback
  - RicoChatAPI uses profile_repo (not self.memory) for load/save
"""
from __future__ import annotations

import os
import sys
from dataclasses import asdict
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rico_agent import RicoAgentSettings, RicoProfile
from src.models.onboarding import ONBOARDING_IN_PROGRESS, ONBOARDING_COMPLETED


# ── Helpers ────────────────────────────────────────────────────────────────────

def _bundle(
    external_user_id="u@x.com",
    name="Test User",
    email="u@x.com",
    db_id="db-uuid-1",
    profile=None,
    settings=None,
) -> dict:
    return {
        "id": db_id,
        "external_user_id": external_user_id,
        "name": name,
        "email": email,
        "phone": None,
        "telegram_username": None,
        "profile": profile or {"target_roles": ["HSE Manager"], "skills": ["ISO 45001"]},
        "settings": settings or {"autonomy_level": "recommend_only", "match_strictness": "balanced"},
    }


def _mock_db(bundle=None, available=True):
    db = MagicMock()
    db.available = available
    db.get_user_bundle.return_value = bundle
    db.upsert_user.return_value = {"id": "db-uuid-1"}
    return db


def _mock_mem(profile=None):
    mem = MagicMock()
    mem.load_profile.return_value = profile
    mem.upsert_profile_from_dict.return_value = profile or RicoProfile(user_id="u@x.com")
    return mem


# ── get_profile ────────────────────────────────────────────────────────────────

class TestGetProfile:
    def test_returns_db_profile_when_available(self):
        from src.repositories.profile_repo import get_profile
        b = _bundle()
        with patch("src.repositories.profile_repo._db", return_value=_mock_db(bundle=b)), \
             patch("src.repositories.profile_repo._memory"):
            result = get_profile("u@x.com")
        assert result is not None
        assert result.user_id == "u@x.com"
        assert result.name == "Test User"
        assert result.target_roles == ["HSE Manager"]

    def test_falls_back_to_json_when_db_returns_none(self):
        from src.repositories.profile_repo import get_profile
        json_profile = RicoProfile(user_id="u@x.com", name="JSON User")
        mem = _mock_mem(profile=json_profile)
        with patch("src.repositories.profile_repo._db", return_value=_mock_db(bundle=None)), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            result = get_profile("u@x.com")
        assert result is not None
        assert result.name == "JSON User"

    def test_falls_back_to_json_when_db_unavailable(self):
        from src.repositories.profile_repo import get_profile
        json_profile = RicoProfile(user_id="u@x.com")
        mem = _mock_mem(profile=json_profile)
        with patch("src.repositories.profile_repo._db", return_value=None), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            result = get_profile("u@x.com")
        assert result is not None

    def test_returns_none_when_both_unavailable(self):
        from src.repositories.profile_repo import get_profile
        mem = _mock_mem(profile=None)
        with patch("src.repositories.profile_repo._db", return_value=None), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            result = get_profile("ghost@x.com")
        assert result is None

    def test_falls_back_to_json_on_db_exception(self):
        from src.repositories.profile_repo import get_profile
        db = _mock_db()
        db.get_user_bundle.side_effect = RuntimeError("DB error")
        json_profile = RicoProfile(user_id="u@x.com")
        mem = _mock_mem(profile=json_profile)
        with patch("src.repositories.profile_repo._db", return_value=db), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            result = get_profile("u@x.com")
        assert result is not None

    def test_db_settings_mapped_to_agent_settings(self):
        from src.repositories.profile_repo import get_profile
        b = _bundle(settings={"autonomy_level": "auto", "match_strictness": "strict"})
        with patch("src.repositories.profile_repo._db", return_value=_mock_db(bundle=b)), \
             patch("src.repositories.profile_repo._memory"):
            result = get_profile("u@x.com")
        assert result.settings.autonomy_level == "auto"
        assert result.settings.match_strictness == "strict"


# ── upsert_profile ─────────────────────────────────────────────────────────────

class TestUpsertProfile:
    def test_writes_to_json_mirror_always(self):
        from src.repositories.profile_repo import upsert_profile
        mem = _mock_mem()
        with patch("src.repositories.profile_repo._db", return_value=None), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            upsert_profile("u@x.com", {"name": "Test"})
        mem.upsert_profile_from_dict.assert_called_once()

    def test_writes_user_to_db(self):
        from src.repositories.profile_repo import upsert_profile
        db = _mock_db()
        db.upsert_profile = MagicMock()
        mem = _mock_mem()
        with patch("src.repositories.profile_repo._db", return_value=db), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            upsert_profile("u@x.com", {"name": "Test", "email": "u@x.com"})
        db.upsert_user.assert_called_once()
        args = db.upsert_user.call_args[0][0]
        assert args["external_user_id"] == "u@x.com"
        assert args["email"] == "u@x.com"

    def test_writes_profile_fields_to_db(self):
        from src.repositories.profile_repo import upsert_profile
        db = _mock_db()
        db.upsert_profile = MagicMock()
        mem = _mock_mem()
        with patch("src.repositories.profile_repo._db", return_value=db), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            upsert_profile("u@x.com", {"target_roles": ["HSE"], "skills": ["ISO"]})
        db.upsert_profile.assert_called_once()
        profile_data = db.upsert_profile.call_args[0][1]
        assert profile_data["target_roles"] == ["HSE"]

    def test_writes_settings_to_db(self):
        from src.repositories.profile_repo import upsert_profile
        db = _mock_db()
        db.upsert_settings = MagicMock()
        mem = _mock_mem()
        with patch("src.repositories.profile_repo._db", return_value=db), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            upsert_profile("u@x.com", {"autonomy_level": "auto"})
        db.upsert_settings.assert_called_once()

    def test_db_failure_does_not_raise(self):
        from src.repositories.profile_repo import upsert_profile
        db = _mock_db()
        db.upsert_user.side_effect = RuntimeError("DB down")
        mem = _mock_mem()
        with patch("src.repositories.profile_repo._db", return_value=db), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            result = upsert_profile("u@x.com", {"name": "Test"})  # must not raise
        assert result is not None


# ── get_preferences ────────────────────────────────────────────────────────────

class TestGetPreferences:
    def test_returns_db_settings(self):
        from src.repositories.profile_repo import get_preferences
        b = _bundle(settings={"match_strictness": "strict", "autonomy_level": "auto"})
        with patch("src.repositories.profile_repo._db", return_value=_mock_db(bundle=b)), \
             patch("src.repositories.profile_repo._memory"):
            prefs = get_preferences("u@x.com")
        assert prefs["match_strictness"] == "strict"
        assert prefs["autonomy_level"] == "auto"

    def test_falls_back_to_json_settings_when_no_db_bundle(self):
        from src.repositories.profile_repo import get_preferences
        profile = RicoProfile(user_id="u@x.com",
                              settings=RicoAgentSettings(match_strictness="strict"))
        mem = _mock_mem(profile=profile)
        with patch("src.repositories.profile_repo._db", return_value=_mock_db(bundle=None)), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            prefs = get_preferences("u@x.com")
        assert prefs["match_strictness"] == "strict"

    def test_returns_empty_dict_when_both_unavailable(self):
        from src.repositories.profile_repo import get_preferences
        mem = _mock_mem(profile=None)
        with patch("src.repositories.profile_repo._db", return_value=None), \
             patch("src.repositories.profile_repo._memory", return_value=mem):
            prefs = get_preferences("ghost@x.com")
        assert prefs == {}


# ── save_preferences ───────────────────────────────────────────────────────────

class TestSavePreferences:
    def test_upserts_via_db(self):
        from src.repositories.profile_repo import save_preferences
        db = _mock_db()
        with patch("src.repositories.profile_repo._db", return_value=db):
            save_preferences("u@x.com", {"match_strictness": "strict"})
        db.upsert_user.assert_called_once()
        db.upsert_settings.assert_called_once()

    def test_silent_when_db_unavailable(self):
        from src.repositories.profile_repo import save_preferences
        with patch("src.repositories.profile_repo._db", return_value=None):
            save_preferences("u@x.com", {"match_strictness": "strict"})  # must not raise


# ── save_search / list_saved_searches ─────────────────────────────────────────

class TestSavedSearches:
    def test_save_search_inserts_row(self):
        from src.repositories.profile_repo import save_search
        db = _mock_db(bundle=_bundle())
        conn = MagicMock()
        db.connect.return_value.__enter__ = MagicMock(return_value=conn)
        db.connect.return_value.__exit__ = MagicMock(return_value=False)
        with patch("src.repositories.profile_repo._db", return_value=db), \
             patch("src.repositories.profile_repo.psycopg2", create=True):
            save_search("u@x.com", "HSE Manager Dubai")
        db.upsert_user.assert_called_once()

    def test_save_search_silent_when_db_unavailable(self):
        from src.repositories.profile_repo import save_search
        with patch("src.repositories.profile_repo._db", return_value=None):
            save_search("u@x.com", "query")  # must not raise

    def test_list_saved_searches_returns_empty_when_db_unavailable(self):
        from src.repositories.profile_repo import list_saved_searches
        with patch("src.repositories.profile_repo._db", return_value=None):
            result = list_saved_searches("u@x.com")
        assert result == []

    def test_list_saved_searches_returns_empty_when_no_user(self):
        from src.repositories.profile_repo import list_saved_searches
        with patch("src.repositories.profile_repo._db", return_value=_mock_db(bundle=None)):
            result = list_saved_searches("ghost@x.com")
        assert result == []


# ── RicoChatAPI uses profile_repo ──────────────────────────────────────────────

class TestRicoChatAPIUsesProfileRepo:
    def _make_api(self):
        from src.rico_chat_api import RicoChatAPI
        api = RicoChatAPI.__new__(RicoChatAPI)
        api.memory = MagicMock()
        api.agent = MagicMock()
        api.system = MagicMock()
        api.system.run_for_profile.return_value = {"matches": []}
        return api

    def test_new_user_calls_upsert_profile_not_memory(self):
        api = self._make_api()
        with patch("src.rico_chat_api.get_profile", return_value=None) as mock_get, \
             patch("src.rico_chat_api.upsert_profile") as mock_upsert, \
             patch("src.rico_chat_api.is_onboarding_complete", return_value=False), \
             patch("src.rico_chat_api.set_onboarding_status"), \
             patch("src.rico_chat_api.mark_onboarding_complete"):
            api.process_message("new@x.com", "hello")
        mock_get.assert_called_with("new@x.com")
        mock_upsert.assert_called_once()
        api.memory.load_profile.assert_not_called()

    def test_completed_user_calls_get_profile_not_memory(self):
        api = self._make_api()
        with patch("src.rico_chat_api.get_profile", return_value=RicoProfile(user_id="u@x.com")) as mock_get, \
             patch("src.rico_chat_api.is_onboarding_complete", return_value=True), \
             patch("src.rico_chat_api.mark_onboarding_complete"):
            api.process_message("u@x.com", "find jobs")
        mock_get.assert_called()
        api.memory.load_profile.assert_not_called()

    def test_cv_upload_calls_upsert_profile_not_memory(self):
        api = self._make_api()
        with patch("src.rico_chat_api.get_profile", return_value=None), \
             patch("src.rico_chat_api.upsert_profile") as mock_upsert, \
             patch("src.rico_chat_api.is_onboarding_complete", return_value=False), \
             patch("src.rico_chat_api.mark_onboarding_complete"):
            api.process_message("cv@x.com", "my cv is Resume.pdf")
        mock_upsert.assert_called_once()
        api.memory.upsert_profile_from_dict.assert_not_called()
