"""
tests/test_jwt_user_isolation.py
JWT-derived user isolation enforcement tests.

Invariants verified:
  - get_current_user_id returns JWT sub claim as user_id
  - get_current_user_id raises 401 for missing token
  - get_current_user_id raises 401 for invalid/expired token
  - Authenticated routes pass JWT-derived user_id to repo (never None)
  - Cross-user data leakage: alice cannot see bob's applications
  - DB unavailable → 503 (no JSON fallback on SaaS path)
  - User not found in DB → 404 (no JSON fallback on SaaS path)
  - /api/v1/stats uses JWT-derived user_id (not global JSON)
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_token(email: str, role: str = "user") -> str:
    from src.api.auth import create_access_token
    return create_access_token({"sub": email, "role": role})


def _client_with_token(email: str) -> tuple:
    from src.api.app import app
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies.set("access_token", _make_token(email))
    return tc


def _mock_db_for(user_id: str, recs: list) -> MagicMock:
    db = MagicMock()
    db.available = True
    db.get_user_bundle.side_effect = lambda uid: {"id": f"uuid-{uid}"} if uid == user_id else None
    db.get_recommendations.return_value = recs
    db.get_recommendation_stats.return_value = {"total": len(recs)}
    db.update_recommendation_status.return_value = True
    return db


# ── get_current_user_id dependency unit tests ─────────────────────────────────

class TestGetCurrentUserIdDep:
    def _request_with_cookie(self, cookie_value: str) -> Request:
        scope = {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "GET",
        }
        req = Request(scope)
        req._cookies = {"access_token": cookie_value} if cookie_value else {}
        return req

    def test_valid_token_returns_email(self):
        from src.api.deps import get_current_user_id
        token = _make_token("alice@rico.ai")
        req = self._request_with_cookie(token)
        assert get_current_user_id(req) == "alice@rico.ai"

    def test_missing_cookie_raises_401(self):
        from src.api.deps import get_current_user_id
        req = self._request_with_cookie("")
        req._cookies = {}
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id(req)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        from src.api.deps import get_current_user_id
        req = self._request_with_cookie("not.a.valid.jwt")
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_id(req)
        assert exc_info.value.status_code == 401

    def test_different_users_get_different_ids(self):
        from src.api.deps import get_current_user_id
        req_alice = self._request_with_cookie(_make_token("alice@rico.ai"))
        req_bob = self._request_with_cookie(_make_token("bob@rico.ai"))
        assert get_current_user_id(req_alice) != get_current_user_id(req_bob)
        assert get_current_user_id(req_alice) == "alice@rico.ai"
        assert get_current_user_id(req_bob) == "bob@rico.ai"


# ── Route-level enforcement ───────────────────────────────────────────────────

class TestApplicationsRouteIsolation:
    def test_unauthenticated_request_rejected(self):
        from src.api.app import app
        tc = TestClient(app, raise_server_exceptions=False)
        r = tc.get("/api/v1/applications")
        assert r.status_code == 401

    def test_alice_gets_her_own_applications(self):
        alice_recs = [{"job_id": "j1", "title": "HSE Manager", "status": "applied"}]
        db = _mock_db_for("alice@rico.ai", alice_recs)
        tc = _client_with_token("alice@rico.ai")
        with patch("src.repositories.applications_repo._db", return_value=db):
            r = tc.get("/api/v1/applications")
        assert r.status_code == 200
        assert r.json()["applications"] == alice_recs

    def test_bob_cannot_see_alices_applications(self):
        alice_recs = [{"job_id": "j1", "title": "HSE Manager", "status": "applied"}]
        bob_recs = [{"job_id": "j2", "title": "Safety Officer", "status": "saved"}]

        def _db_side_effect():
            db = MagicMock()
            db.available = True
            db.get_user_bundle.side_effect = lambda uid: {"id": f"uuid-{uid}"}
            db.get_recommendations.side_effect = lambda uid, **kw: (
                alice_recs if uid == "uuid-alice@rico.ai" else
                bob_recs if uid == "uuid-bob@rico.ai" else []
            )
            return db

        tc_alice = _client_with_token("alice@rico.ai")
        tc_bob = _client_with_token("bob@rico.ai")

        with patch("src.repositories.applications_repo._db", side_effect=_db_side_effect):
            r_alice = tc_alice.get("/api/v1/applications")
            r_bob = tc_bob.get("/api/v1/applications")

        assert r_alice.status_code == 200
        assert r_bob.status_code == 200
        assert r_alice.json()["applications"] == alice_recs
        assert r_bob.json()["applications"] == bob_recs
        assert r_alice.json()["applications"] != r_bob.json()["applications"]

    def test_db_unavailable_returns_503(self):
        tc = _client_with_token("alice@rico.ai")
        with patch("src.repositories.applications_repo._db", return_value=None):
            r = tc.get("/api/v1/applications")
        assert r.status_code == 503

    def test_new_auth_user_auto_provisioned_returns_200(self):
        """New auth user with no rico_users row is auto-provisioned and gets empty list."""
        db = MagicMock()
        db.available = True
        db.get_user_bundle.return_value = None
        db.upsert_user.return_value = {"id": "new-uuid"}
        db.get_recommendations.return_value = []
        tc = _client_with_token("newuser@rico.ai")
        with patch("src.repositories.applications_repo._db", return_value=db):
            r = tc.get("/api/v1/applications")
        assert r.status_code == 200
        assert r.json()["applications"] == []
        db.upsert_user.assert_called_once()

    def test_jwt_user_id_passed_to_repo_not_none(self):
        """The route must never call get_all without user_id."""
        tc = _client_with_token("alice@rico.ai")
        with patch("src.api.routers.applications.get_all") as mock_get_all:
            mock_get_all.return_value = []
            tc.get("/api/v1/applications")
        assert mock_get_all.called
        call_kwargs = mock_get_all.call_args[1]
        assert call_kwargs.get("user_id") == "alice@rico.ai"


class TestStatsRouteIsolation:
    def test_unauthenticated_request_rejected(self):
        from src.api.app import app
        tc = TestClient(app, raise_server_exceptions=False)
        r = tc.get("/api/v1/stats")
        assert r.status_code == 401

    def test_stats_route_passes_jwt_user_id(self):
        """GET /api/v1/stats must pass JWT-derived user_id, not call global get_stats()."""
        tc = _client_with_token("alice@rico.ai")
        with patch("src.api.routers.stats.get_stats") as mock_stats:
            mock_stats.return_value = {"total": 3}
            r = tc.get("/api/v1/stats")
        assert r.status_code == 200
        assert mock_stats.called
        call_kwargs = mock_stats.call_args[1]
        assert call_kwargs.get("user_id") == "alice@rico.ai"

    def test_stats_db_unavailable_returns_503(self):
        tc = _client_with_token("alice@rico.ai")
        with patch("src.repositories.applications_repo._db", return_value=None):
            r = tc.get("/api/v1/stats")
        assert r.status_code == 503


class TestSettingsRouteIsolation:
    def test_unauthenticated_read_rejected(self):
        from src.api.app import app
        tc = TestClient(app, raise_server_exceptions=False)
        r = tc.get("/api/v1/settings")
        assert r.status_code == 401

    def test_unauthenticated_write_rejected(self):
        from src.api.app import app
        tc = TestClient(app, raise_server_exceptions=False)
        r = tc.put("/api/v1/settings", json={"min_score": 60})
        assert r.status_code == 401

    def test_settings_read_passes_jwt_user_id(self):
        tc = _client_with_token("alice@rico.ai")
        with patch("src.api.routers.settings.get_settings") as mock_get:
            mock_get.return_value = {"min_score": 50}
            tc.get("/api/v1/settings")
        assert mock_get.called
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs.get("user_id") == "alice@rico.ai"

    def test_settings_write_passes_jwt_user_id(self):
        tc = _client_with_token("alice@rico.ai")
        with patch("src.api.routers.settings.update_settings") as mock_update:
            mock_update.return_value = {"min_score": 70}
            tc.put("/api/v1/settings", json={"min_score": 70})
        assert mock_update.called
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs.get("user_id") == "alice@rico.ai"

    def test_two_users_get_different_settings(self):
        """Settings read for alice must not leak bob's data."""
        _base = {
            "include_keywords": [],
            "exclude_keywords": [],
            "max_daily_applies": 5,
            "telegram_chat_id": "",
            "score_threshold_apply": 70,
            "score_threshold_watch": 50,
        }

        def _settings_side_effect(user_id: str):
            if user_id == "alice@rico.ai":
                return {**_base, "min_score": 70}
            if user_id == "bob@rico.ai":
                return {**_base, "min_score": 40}
            return {**_base, "min_score": 50}

        tc_alice = _client_with_token("alice@rico.ai")
        tc_bob = _client_with_token("bob@rico.ai")

        with patch("src.api.routers.settings.get_settings", side_effect=_settings_side_effect):
            r_alice = tc_alice.get("/api/v1/settings")
            r_bob = tc_bob.get("/api/v1/settings")

        assert r_alice.status_code == 200
        assert r_bob.status_code == 200
        assert r_alice.json()["min_score"] == 70
        assert r_bob.json()["min_score"] == 40


# ── applications_repo direct — fallback removal contract ─────────────────────

class TestApplicationsRepoFallbackRemoval:
    def test_get_all_with_user_id_db_unavailable_raises_503(self):
        from src.repositories.applications_repo import get_all
        with patch("src.repositories.applications_repo._db", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                get_all(user_id="alice@rico.ai")
        assert exc_info.value.status_code == 503

    def test_get_all_new_auth_user_auto_provisioned(self):
        """P1: user in auth table but not rico_users → auto-provision, return empty list."""
        from src.repositories.applications_repo import get_all
        db = MagicMock()
        db.get_user_bundle.return_value = None
        db.upsert_user.return_value = {"id": "new-uuid"}
        db.get_recommendations.return_value = []
        with patch("src.repositories.applications_repo._db", return_value=db):
            result = get_all(user_id="newuser@rico.ai")
        assert result == []
        db.upsert_user.assert_called_once()
        call_payload = db.upsert_user.call_args[0][0]
        assert call_payload["email"] == "newuser@rico.ai"
        assert call_payload["source"] == "auth_register"

    def test_get_all_resolver_db_exception_raises_503_not_404(self):
        """P2: transient DB error in resolver must surface as 503, not 404."""
        from src.repositories.applications_repo import get_all
        db = MagicMock()
        db.get_user_bundle.side_effect = Exception("connection timeout")
        with patch("src.repositories.applications_repo._db", return_value=db):
            with pytest.raises(HTTPException) as exc_info:
                get_all(user_id="alice@rico.ai")
        assert exc_info.value.status_code == 503

    def test_get_stats_with_user_id_db_unavailable_raises_503(self):
        from src.repositories.applications_repo import get_stats
        with patch("src.repositories.applications_repo._db", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                get_stats(user_id="alice@rico.ai")
        assert exc_info.value.status_code == 503

    def test_find_by_job_id_with_user_id_db_unavailable_raises_503(self):
        from src.repositories.applications_repo import find_by_job_id
        with patch("src.repositories.applications_repo._db", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                find_by_job_id("j1", user_id="alice@rico.ai")
        assert exc_info.value.status_code == 503

    def test_update_status_with_user_id_db_unavailable_raises_503(self):
        from src.repositories.applications_repo import update_status
        with patch("src.repositories.applications_repo._db", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                update_status({"job_id": "j1"}, "applied", user_id="alice@rico.ai")
        assert exc_info.value.status_code == 503

    def test_get_all_without_user_id_still_uses_json_legacy(self):
        """Legacy path: no user_id → JSON store, no exception."""
        from src.repositories.applications_repo import get_all
        legacy = [{"job_id": "legacy1"}]
        with patch("src.repositories.applications_repo._get_applied", return_value=legacy):
            result = get_all()
        assert result == legacy

    def test_get_all_does_not_cross_contaminate_users(self):
        """get_all for alice must never return bob's rows."""
        from src.repositories.applications_repo import get_all

        alice_recs = [{"job_id": "a1"}]
        bob_recs = [{"job_id": "b1"}]

        def _db_factory():
            db = MagicMock()
            db.get_user_bundle.side_effect = lambda uid: {"id": f"uuid-{uid}"}
            db.get_recommendations.side_effect = lambda uid, **kw: (
                alice_recs if uid == "uuid-alice@rico.ai" else
                bob_recs if uid == "uuid-bob@rico.ai" else []
            )
            return db

        with patch("src.repositories.applications_repo._db", side_effect=_db_factory):
            r_alice = get_all(user_id="alice@rico.ai")
            r_bob = get_all(user_id="bob@rico.ai")

        assert r_alice == alice_recs
        assert r_bob == bob_recs
        assert r_alice != r_bob
