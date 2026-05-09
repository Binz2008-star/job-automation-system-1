"""
tests/test_users_auth.py
Tests for DB-backed authentication, role claims, and user registration.

All DB calls are patched — no real database required.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ADMIN_EMAIL",    "admin@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass123")
os.environ.setdefault("JWT_SECRET",     "x" * 32)

from src.repositories.users_repo import User

_DB_USER = User(
    id=1,
    email="alice@rico.ai",
    password_hash="$2b$12$placeholder",   # will be replaced by mock
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    last_login_at=None,
)

_ADMIN_USER = User(
    id=2,
    email="admin@rico.ai",
    password_hash="$2b$12$placeholder",
    role="admin",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    last_login_at=None,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_admin_client():
    from fastapi.testclient import TestClient
    from src.api.app import app
    from src.api.auth import create_access_token
    token = create_access_token({"sub": "admin@test.com", "role": "admin"})
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies.set("access_token", token)
    return tc


def _make_user_client():
    from fastapi.testclient import TestClient
    from src.api.app import app
    from src.api.auth import create_access_token
    token = create_access_token({"sub": "user@test.com", "role": "user"})
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies.set("access_token", token)
    return tc


def _make_legacy_client():
    """JWT issued before roles were added — no 'role' claim."""
    from fastapi.testclient import TestClient
    from src.api.app import app
    from src.api.auth import create_access_token
    token = create_access_token({"sub": "legacy@test.com"})   # no role key
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies.set("access_token", token)
    return tc


@pytest.fixture(scope="module")
def admin_client():
    return _make_admin_client()


@pytest.fixture(scope="module")
def user_client():
    return _make_user_client()


@pytest.fixture(scope="module")
def legacy_client():
    return _make_legacy_client()


# ── verify_credentials ────────────────────────────────────────────────────────

class TestVerifyCredentials:
    def test_db_path_success(self):
        from src.api.auth import verify_credentials
        with patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER), \
             patch("src.repositories.users_repo.update_last_login"), \
             patch("src.api.auth._PWD_CTX.verify", return_value=True):
            result = verify_credentials("alice@rico.ai", "correctpass")
        assert result is not None
        assert result["email"] == "alice@rico.ai"
        assert result["role"] == "user"

    def test_db_path_wrong_password(self):
        from src.api.auth import verify_credentials
        with patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER), \
             patch("src.repositories.users_repo.update_last_login"), \
             patch("src.api.auth._PWD_CTX.verify", return_value=False):
            result = verify_credentials("alice@rico.ai", "wrongpass")
        assert result is None

    def test_env_fallback_when_db_unavailable(self):
        from src.api.auth import verify_credentials
        env = {"ADMIN_EMAIL": "admin@test.com", "ADMIN_PASSWORD": "TestPass123", "ADMIN_PASSWORD_HASH": ""}
        with patch("src.repositories.users_repo.get_user_by_email", return_value=None), \
             patch.dict(os.environ, env, clear=False):
            result = verify_credentials("admin@test.com", "TestPass123")
        assert result is not None
        assert result["email"] == "admin@test.com"
        assert result["role"] == "admin"

    def test_env_fallback_wrong_password(self):
        from src.api.auth import verify_credentials
        env = {"ADMIN_EMAIL": "admin@test.com", "ADMIN_PASSWORD": "TestPass123", "ADMIN_PASSWORD_HASH": ""}
        with patch("src.repositories.users_repo.get_user_by_email", return_value=None), \
             patch.dict(os.environ, env, clear=False):
            result = verify_credentials("admin@test.com", "wrongpass")
        assert result is None

    def test_unknown_email_returns_none(self):
        from src.api.auth import verify_credentials
        env = {"ADMIN_EMAIL": "admin@test.com", "ADMIN_PASSWORD_HASH": ""}
        with patch("src.repositories.users_repo.get_user_by_email", return_value=None), \
             patch.dict(os.environ, env, clear=False):
            result = verify_credentials("nobody@example.com", "pass")
        assert result is None

    def test_db_error_falls_back_to_env(self):
        from src.api.auth import verify_credentials
        env = {"ADMIN_EMAIL": "admin@test.com", "ADMIN_PASSWORD": "TestPass123", "ADMIN_PASSWORD_HASH": ""}
        with patch("src.repositories.users_repo.get_user_by_email",
                   side_effect=Exception("db down")), \
             patch.dict(os.environ, env, clear=False):
            result = verify_credentials("admin@test.com", "TestPass123")
        assert result is not None
        assert result["role"] == "admin"


# ── Role claim in JWT ─────────────────────────────────────────────────────────

class TestJWTRoleClaim:
    def test_login_embeds_role_in_token(self):
        from fastapi.testclient import TestClient
        from src.api.app import app
        from src.api.rate_limit import limiter
        limiter._storage.reset()   # other test files exhaust the 5/min login quota
        tc = TestClient(app, raise_server_exceptions=False)
        with patch("src.api.auth.verify_credentials",
                   return_value={"email": "admin@test.com", "role": "admin"}):
            r = tc.post("/api/v1/auth/login",
                        json={"email": "admin@test.com", "password": "TestPass123"})
        assert r.status_code == 200
        cookie = r.cookies.get("access_token")
        assert cookie is not None
        from src.api.auth import decode_access_token
        payload = decode_access_token(cookie)
        assert payload["role"] == "admin"

    def test_get_current_user_returns_role(self, admin_client):
        r = admin_client.get("/api/v1/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_legacy_token_without_role_defaults_to_user(self, legacy_client):
        r = legacy_client.get("/api/v1/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "user"

    def test_user_role_reflected_correctly(self, user_client):
        r = user_client.get("/api/v1/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "user"


# ── require_admin dependency ──────────────────────────────────────────────────

class TestRequireAdmin:
    def test_admin_can_reach_register(self, admin_client):
        with patch("src.repositories.users_repo.get_user_by_email", return_value=None), \
             patch("src.api.auth._PWD_CTX.hash", return_value="$2b$12$fakehash"), \
             patch("src.repositories.users_repo.create_user", return_value=User(
                 id=99, email="new@rico.ai", password_hash="$2b$12$fakehash",
                 role="user", is_active=True,
                 created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                 last_login_at=None,
             )):
            r = admin_client.post("/api/v1/auth/register",
                                  json={"email": "new@rico.ai", "password": "SecurePass1"})
        assert r.status_code == 201

    def test_non_admin_blocked_from_register(self, user_client):
        r = user_client.post("/api/v1/auth/register",
                             json={"email": "hacker@rico.ai", "password": "pass1234"})
        assert r.status_code == 403

    def test_unauthenticated_blocked_from_register(self):
        from fastapi.testclient import TestClient
        from src.api.app import app
        tc = TestClient(app, raise_server_exceptions=False)
        r = tc.post("/api/v1/auth/register",
                    json={"email": "anon@rico.ai", "password": "pass1234"})
        assert r.status_code == 401


# ── Register endpoint ─────────────────────────────────────────────────────────

class TestRegisterEndpoint:
    def test_register_returns_201_with_user_fields(self, admin_client):
        created = User(
            id=10, email="newuser@rico.ai", password_hash="$2b$12$fakehash",
            role="user", is_active=True,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_login_at=None,
        )
        with patch("src.repositories.users_repo.get_user_by_email", return_value=None), \
             patch("src.api.auth._PWD_CTX.hash", return_value="$2b$12$fakehash"), \
             patch("src.repositories.users_repo.create_user", return_value=created):
            r = admin_client.post("/api/v1/auth/register",
                                  json={"email": "newuser@rico.ai", "password": "SecurePass1"})
        assert r.status_code == 201
        data = r.json()
        assert data["email"] == "newuser@rico.ai"
        assert data["role"] == "user"
        assert data["created"] is True

    def test_register_duplicate_returns_409(self, admin_client):
        with patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER):
            r = admin_client.post("/api/v1/auth/register",
                                  json={"email": "alice@rico.ai", "password": "SecurePass1"})
        assert r.status_code == 409

    def test_register_db_unavailable_returns_503(self, admin_client):
        with patch("src.repositories.users_repo.get_user_by_email", return_value=None), \
             patch("src.api.auth._PWD_CTX.hash", return_value="$2b$12$fakehash"), \
             patch("src.repositories.users_repo.create_user", return_value=None):
            r = admin_client.post("/api/v1/auth/register",
                                  json={"email": "dbdown@rico.ai", "password": "SecurePass1"})
        assert r.status_code == 503

    def test_register_short_password_returns_422(self, admin_client):
        r = admin_client.post("/api/v1/auth/register",
                              json={"email": "weak@rico.ai", "password": "short"})
        assert r.status_code == 422

    def test_register_admin_role(self, admin_client):
        created = User(
            id=11, email="newadmin@rico.ai", password_hash="$2b$12$fakehash",
            role="admin", is_active=True,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_login_at=None,
        )
        with patch("src.repositories.users_repo.get_user_by_email", return_value=None), \
             patch("src.api.auth._PWD_CTX.hash", return_value="$2b$12$fakehash"), \
             patch("src.repositories.users_repo.create_user", return_value=created):
            r = admin_client.post("/api/v1/auth/register",
                                  json={"email": "newadmin@rico.ai",
                                        "password": "SecurePass1", "role": "admin"})
        assert r.status_code == 201
        assert r.json()["role"] == "admin"


# ── users_repo unit tests ─────────────────────────────────────────────────────

class TestUsersRepo:
    def test_get_user_by_email_returns_none_when_db_unavailable(self):
        from src.repositories.users_repo import get_user_by_email
        with patch("src.db.is_db_available", return_value=False):
            result = get_user_by_email("any@example.com")
        assert result is None

    def test_get_user_by_email_returns_none_on_no_connection(self):
        from src.repositories.users_repo import get_user_by_email
        with patch("src.db.is_db_available", return_value=True), \
             patch("src.db.get_db_connection", return_value=None):
            result = get_user_by_email("any@example.com")
        assert result is None

    def test_create_user_returns_none_when_db_unavailable(self):
        from src.repositories.users_repo import create_user
        with patch("src.db.is_db_available", return_value=False):
            result = create_user("new@rico.ai", "hash")
        assert result is None

    def test_update_last_login_silently_skips_when_db_unavailable(self):
        from src.repositories.users_repo import update_last_login
        with patch("src.db.is_db_available", return_value=False):
            update_last_login(1)  # must not raise
