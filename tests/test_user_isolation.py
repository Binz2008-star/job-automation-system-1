"""
tests/test_user_isolation.py
Verify that Rico services isolate data per user in the SaaS path.

All DB calls are patched — no real database required.
Invariants verified:
  - Two users scoring the same job with different profiles get different scores
  - applications_repo returns different data for different user_ids
  - applications_repo falls back to legacy global JSON when user_id omitted
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rico_agent import RicoAgent, RicoProfile, RicoAgentSettings


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_db_for_user(recommendations, available=True):
    """Return a mock RicoDB that serves per-user recommendations."""
    db = MagicMock()
    db.available = available
    db.get_recommendations.return_value = recommendations
    db.get_recommendation_stats.return_value = {
        "total": len(recommendations),
        "by_status": {},
        "applied": 0,
        "saved": 0,
        "interview": 0,
        "rejected": 0,
        "offer": 0,
    }
    db.update_recommendation_status.return_value = True
    return db


def _make_profile(user_id, target_roles, skills, preferred_cities, green_flags=None, red_flags=None):
    return RicoProfile(
        user_id=user_id,
        target_roles=target_roles,
        skills=skills,
        preferred_cities=preferred_cities,
        green_flags=green_flags or [],
        red_flags=red_flags or [],
        settings=RicoAgentSettings(),
    )


# ── Scoring isolation ──────────────────────────────────────────────────────────

class TestUserScoringIsolation:
    def test_two_users_score_same_job_differently(self):
        """Different profiles must produce different scores for the same job."""
        job = {
            "title": "HSE Manager",
            "description": "Lead safety operations in Dubai. ISO 45001 experience required.",
            "location": "Dubai, UAE",
        }

        agent = RicoAgent()

        user_a = _make_profile(
            "alice@rico.ai",
            target_roles=["HSE Manager", "Safety Manager"],
            skills=["ISO 45001", "risk assessment", "Dubai"],
            preferred_cities=["Dubai"],
        )

        user_b = _make_profile(
            "bob@rico.ai",
            target_roles=["Software Engineer", "Data Scientist"],
            skills=["Python", "machine learning"],
            preferred_cities=["San Francisco"],
        )

        score_a = agent._score_job(user_a, job)["score"]
        score_b = agent._score_job(user_b, job)["score"]

        assert score_a != score_b
        assert score_a > score_b  # Alice should score higher for HSE role

    def test_user_with_matching_role_gets_higher_score(self):
        """Profile with direct role match should outscore a generic profile."""
        job = {"title": "QHSE Manager", "description": "Quality and safety in Abu Dhabi.", "location": "Abu Dhabi"}

        agent = RicoAgent()

        matched = _make_profile(
            "matched@rico.ai",
            target_roles=["QHSE Manager"],
            skills=["ISO 9001"],
            preferred_cities=["Abu Dhabi"],
        )

        generic = _make_profile(
            "generic@rico.ai",
            target_roles=["Nurse", "Doctor"],
            skills=["patient care"],
            preferred_cities=["London"],
        )

        score_matched = agent._score_job(matched, job)["score"]
        score_generic = agent._score_job(generic, job)["score"]

        assert score_matched > score_generic

    def test_green_flags_boost_score(self):
        """Green flags in the profile should increase the score when present in job."""
        job = {"title": "HSE Advisor", "description": "Great work-life balance and remote friendly.", "location": "Dubai"}

        agent = RicoAgent()

        with_flags = _make_profile(
            "flags@rico.ai",
            target_roles=["HSE Advisor"],
            skills=["safety"],
            preferred_cities=["Dubai"],
            green_flags=["remote friendly", "work-life balance"],
        )

        without_flags = _make_profile(
            "noflags@rico.ai",
            target_roles=["HSE Advisor"],
            skills=["safety"],
            preferred_cities=["Dubai"],
        )

        score_with = agent._score_job(with_flags, job)["score"]
        score_without = agent._score_job(without_flags, job)["score"]

        assert score_with > score_without

    def test_red_flags_reduce_score(self):
        """Red flags in the profile should decrease the score when present in job."""
        job = {"title": "HSE Manager", "description": "Night shift required. On-call 24/7.", "location": "Dubai"}

        agent = RicoAgent()

        with_red = _make_profile(
            "red@rico.ai",
            target_roles=["HSE Manager"],
            skills=["safety"],
            preferred_cities=["Dubai"],
            red_flags=["night shift"],
        )

        without_red = _make_profile(
            "nored@rico.ai",
            target_roles=["HSE Manager"],
            skills=["safety"],
            preferred_cities=["Dubai"],
        )

        score_with = agent._score_job(with_red, job)["score"]
        score_without = agent._score_job(without_red, job)["score"]

        assert score_with < score_without


# ── Applications / recommendations isolation ─────────────────────────────────

class TestUserApplicationsIsolation:
    def test_get_all_returns_different_data_per_user(self):
        """applications_repo.get_all must return user-scoped recommendations."""
        from src.repositories import applications_repo

        alice_recs = [{"job_id": "j1", "title": "HSE Manager", "status": "applied"}]
        bob_recs = [{"job_id": "j2", "title": "Safety Officer", "status": "saved"}]

        db = MagicMock()
        db.available = True
        db.get_user_bundle.side_effect = lambda uid: {"id": f"uuid-{uid}"}
        # get_recommendations is called with the resolved UUID
        db.get_recommendations.side_effect = lambda uid, **kw: (
            alice_recs if uid == "uuid-alice@rico.ai" else
            bob_recs if uid == "uuid-bob@rico.ai" else []
        )

        with patch("src.repositories.applications_repo._db", return_value=db):
            alice_apps = applications_repo.get_all(user_id="alice@rico.ai")
            bob_apps = applications_repo.get_all(user_id="bob@rico.ai")

        assert alice_apps == alice_recs
        assert bob_apps == bob_recs
        assert alice_apps != bob_apps

    def test_get_stats_returns_different_counts_per_user(self):
        """applications_repo.get_stats must aggregate per-user."""
        from src.repositories import applications_repo

        db = MagicMock()
        db.available = True
        db.get_user_bundle.side_effect = lambda uid: {"id": f"uuid-{uid}"}
        db.get_recommendation_stats.side_effect = lambda uid: (
            {"total": 5, "applied": 3, "saved": 2} if uid == "uuid-alice@rico.ai" else
            {"total": 1, "applied": 0, "saved": 1} if uid == "uuid-bob@rico.ai" else
            {"total": 0}
        )

        with patch("src.repositories.applications_repo._db", return_value=db):
            alice_stats = applications_repo.get_stats(user_id="alice@rico.ai")
            bob_stats = applications_repo.get_stats(user_id="bob@rico.ai")

        assert alice_stats["total"] == 5
        assert bob_stats["total"] == 1
        assert alice_stats != bob_stats

    def test_find_by_job_id_is_user_scoped(self):
        """find_by_job_id must not leak another user's application."""
        from src.repositories import applications_repo

        alice_recs = [{"job_id": "j1", "title": "HSE Manager", "status": "applied"}]
        bob_recs = [{"job_id": "j2", "title": "Safety Officer", "status": "saved"}]

        db = MagicMock()
        db.available = True
        db.get_user_bundle.side_effect = lambda uid: {"id": f"uuid-{uid}"}
        db.get_recommendations.side_effect = lambda uid, **kw: (
            alice_recs if uid == "uuid-alice@rico.ai" else
            bob_recs if uid == "uuid-bob@rico.ai" else []
        )

        with patch("src.repositories.applications_repo._db", return_value=db):
            found_for_alice = applications_repo.find_by_job_id("j2", user_id="alice@rico.ai")
            found_for_bob = applications_repo.find_by_job_id("j2", user_id="bob@rico.ai")

        assert found_for_alice is None
        assert found_for_bob is not None

    def test_legacy_fallback_when_user_id_omitted(self):
        """When user_id is omitted, the repo must fall back to global JSON store."""
        from src.repositories import applications_repo

        legacy_apps = [{"job_id": "legacy1", "title": "Legacy Job"}]

        with patch("src.repositories.applications_repo._get_applied", return_value=legacy_apps):
            result = applications_repo.get_all()

        assert result == legacy_apps

    def test_db_unavailable_falls_back_to_legacy(self):
        """When Rico DB is unavailable, user-scoped calls must fall back to global JSON."""
        from src.repositories import applications_repo

        legacy_apps = [{"job_id": "fallback1", "title": "Fallback Job"}]

        with patch("src.repositories.applications_repo._db", return_value=None), \
             patch("src.repositories.applications_repo._get_applied", return_value=legacy_apps):
            result = applications_repo.get_all(user_id="any@rico.ai")

        assert result == legacy_apps


# ── Settings isolation ─────────────────────────────────────────────────────────

class TestUserSettingsIsolation:
    def test_settings_repo_reads_per_user(self):
        """settings_repo.read must query the correct user row."""
        from src.repositories import settings_repo

        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = (["hse"], [], 60, 5, "")
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.repositories.settings_repo.get_db_connection", return_value=conn):
            result = settings_repo.read(user_id="alice@rico.ai")

        assert result is not None
        assert result["min_score"] == 60
        # Verify the correct user_id was passed in the SQL query
        call_args = cur.execute.call_args[0][1]
        assert call_args[0] == "alice@rico.ai"

    def test_settings_service_returns_user_specific_values(self):
        """settings_service.get_settings must return the user's DB row when available."""
        from src.services import settings_service

        with patch("src.services.settings_service.is_db_available", return_value=True), \
             patch("src.services.settings_service.settings_repo.read", return_value={"min_score": 70}):
            result = settings_service.get_settings(user_id="alice@rico.ai")

        assert result["min_score"] == 70

    def test_settings_service_fallback_when_no_user_row(self):
        """settings_service.get_settings must return defaults when no DB row exists."""
        from src.services import settings_service

        with patch("src.services.settings_service.is_db_available", return_value=True), \
             patch("src.services.settings_service.settings_repo.read", return_value=None):
            result = settings_service.get_settings(user_id="bob@rico.ai")

        assert result["min_score"] == 50  # default


# ── Legacy fallback warnings ───────────────────────────────────────────────────

class TestLegacyFallbackWarnings:
    def test_get_all_without_user_id_emits_warning(self):
        """Calling get_all without user_id must log LEGACY_FALLBACK_NO_USER_ID."""
        from src.repositories import applications_repo

        with patch("src.repositories.applications_repo._get_applied", return_value=[]), \
             patch("src.repositories.applications_repo.logger.warning") as mock_warn:
            applications_repo.get_all()

        mock_warn.assert_called_once()
        assert "LEGACY_FALLBACK_NO_USER_ID" in str(mock_warn.call_args)

    def test_get_stats_without_user_id_emits_warning(self):
        """Calling get_stats without user_id must log LEGACY_FALLBACK_NO_USER_ID."""
        from src.repositories import applications_repo

        with patch("src.repositories.applications_repo._get_stats", return_value={"total_applied": 0}), \
             patch("src.repositories.applications_repo.logger.warning") as mock_warn:
            applications_repo.get_stats()

        mock_warn.assert_called_once()
        assert "LEGACY_FALLBACK_NO_USER_ID" in str(mock_warn.call_args)

    def test_find_by_job_id_without_user_id_emits_warning(self):
        """Calling find_by_job_id without user_id must log LEGACY_FALLBACK_NO_USER_ID."""
        from src.repositories import applications_repo

        with patch("src.repositories.applications_repo._get_applied", return_value=[]), \
             patch("src.repositories.applications_repo.logger.warning") as mock_warn:
            applications_repo.find_by_job_id("j1")

        mock_warn.assert_called_once()
        assert "LEGACY_FALLBACK_NO_USER_ID" in str(mock_warn.call_args)

    def test_update_status_without_user_id_emits_warning(self):
        """Calling update_status without user_id must log LEGACY_FALLBACK_NO_USER_ID."""
        from src.repositories import applications_repo

        with patch("src.repositories.applications_repo._update_status", return_value=True), \
             patch("src.repositories.applications_repo.logger.warning") as mock_warn:
            applications_repo.update_status({"job_id": "j1"}, "applied")

        mock_warn.assert_called_once()
        assert "LEGACY_FALLBACK_NO_USER_ID" in str(mock_warn.call_args)


# ── Route fail-closed guard ────────────────────────────────────────────────────

class TestAuthenticatedRouteFailClosed:
    def test_applications_list_route_passes_user_id(self):
        """The authenticated /api/v1/applications route must always pass user_id to repo."""
        from fastapi.testclient import TestClient
        from src.api.app import app
        from src.api.auth import create_access_token

        token = create_access_token({"sub": "alice@rico.ai", "role": "user"})
        tc = TestClient(app, raise_server_exceptions=False)
        tc.cookies.set("access_token", token)

        with patch("src.api.routers.applications.get_all") as mock_get_all:
            mock_get_all.return_value = []
            tc.get("/api/v1/applications")

        assert mock_get_all.called
        call_kwargs = mock_get_all.call_args[1]
        assert "user_id" in call_kwargs
        assert call_kwargs["user_id"] == "alice@rico.ai"

    def test_applications_stats_route_passes_user_id(self):
        """The authenticated /api/v1/applications/stats route must always pass user_id to repo."""
        from fastapi.testclient import TestClient
        from src.api.app import app
        from src.api.auth import create_access_token

        token = create_access_token({"sub": "bob@rico.ai", "role": "user"})
        tc = TestClient(app, raise_server_exceptions=False)
        tc.cookies.set("access_token", token)

        with patch("src.api.routers.applications.get_stats") as mock_get_stats:
            mock_get_stats.return_value = {"total": 0}
            tc.get("/api/v1/applications/stats")

        assert mock_get_stats.called
        call_kwargs = mock_get_stats.call_args[1]
        assert "user_id" in call_kwargs
        assert call_kwargs["user_id"] == "bob@rico.ai"

    def test_settings_read_route_passes_user_id(self):
        """The authenticated /api/v1/settings route must always pass user_id to service."""
        from fastapi.testclient import TestClient
        from src.api.app import app
        from src.api.auth import create_access_token

        token = create_access_token({"sub": "alice@rico.ai", "role": "user"})
        tc = TestClient(app, raise_server_exceptions=False)
        tc.cookies.set("access_token", token)

        with patch("src.api.routers.settings.get_settings") as mock_get:
            mock_get.return_value = {"min_score": 50}
            tc.get("/api/v1/settings")

        assert mock_get.called
        call_kwargs = mock_get.call_args[1]
        assert "user_id" in call_kwargs
        assert call_kwargs["user_id"] == "alice@rico.ai"

    def test_settings_write_route_passes_user_id(self):
        """The authenticated PUT /api/v1/settings route must always pass user_id to service."""
        from fastapi.testclient import TestClient
        from src.api.app import app
        from src.api.auth import create_access_token

        token = create_access_token({"sub": "alice@rico.ai", "role": "user"})
        tc = TestClient(app, raise_server_exceptions=False)
        tc.cookies.set("access_token", token)

        with patch("src.api.routers.settings.update_settings") as mock_update:
            mock_update.return_value = {"min_score": 60}
            tc.put("/api/v1/settings", json={"min_score": 60})

        assert mock_update.called
        call_kwargs = mock_update.call_args[1]
        assert "user_id" in call_kwargs
        assert call_kwargs["user_id"] == "alice@rico.ai"
