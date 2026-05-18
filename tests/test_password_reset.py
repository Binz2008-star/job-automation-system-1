"""
tests/test_password_reset.py
Password reset flow: forgot-password and reset-password endpoints.

All DB and repo calls are patched — no real database required.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JWT_SECRET",     "x" * 32)
os.environ.setdefault("ADMIN_EMAIL",    "admin@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass123")
# Ensure production flag is off for most tests
os.environ["RICO_ENV"] = "development"

from fastapi.testclient import TestClient
from src.api.app import app
from src.repositories.users_repo import User

_UTC = timezone.utc

_DB_USER = User(
    id=1,
    email="alice@rico.ai",
    password_hash="$2b$12$placeholder",
    role="user",
    is_active=True,
    created_at=datetime(2026, 1, 1, tzinfo=_UTC),
    last_login_at=None,
)

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset rate limiter state between tests so per-IP limits don't accumulate."""
    from src.api.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()


# ── Helper ────────────────────────────────────────────────────────────────────

def _fake_token() -> str:
    """A plausible-looking token for test fixtures."""
    import secrets
    return secrets.token_urlsafe(32)


# ── POST /forgot-password ─────────────────────────────────────────────────────

class TestForgotPassword:
    URL = "/api/v1/auth/forgot-password"

    def test_unknown_email_returns_generic_success(self):
        """User enumeration must be impossible — same 200 for unknown email."""
        with patch("src.repositories.users_repo.get_user_by_email", return_value=None):
            r = client.post(self.URL, json={"email": "nobody@example.com"})
        assert r.status_code == 200
        assert "reset" in r.json()["message"].lower() or "sent" in r.json()["message"].lower()

    def test_known_email_returns_generic_success(self):
        with (
            patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER),
            patch("src.repositories.password_reset_repo.create_reset_token", return_value=_fake_token()),
        ):
            r = client.post(self.URL, json={"email": "alice@rico.ai"})
        assert r.status_code == 200
        assert "message" in r.json()

    def test_known_email_creates_token(self):
        """Verify that create_reset_token is called for a valid user."""
        with (
            patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER),
            patch("src.repositories.password_reset_repo.create_reset_token", return_value=_fake_token()) as mock_create,
        ):
            client.post(self.URL, json={"email": "alice@rico.ai"})
        mock_create.assert_called_once_with("alice@rico.ai")

    def test_token_not_in_response_body(self):
        """The raw token must never appear in the API response."""
        raw_token = _fake_token()
        with (
            patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER),
            patch("src.repositories.password_reset_repo.create_reset_token", return_value=raw_token),
        ):
            r = client.post(self.URL, json={"email": "alice@rico.ai"})
        assert raw_token not in r.text

    def test_db_failure_still_returns_generic_success(self):
        """Token creation failure must not leak error details to the caller."""
        with (
            patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER),
            patch(
                "src.repositories.password_reset_repo.create_reset_token",
                side_effect=RuntimeError("DB unavailable"),
            ),
        ):
            r = client.post(self.URL, json={"email": "alice@rico.ai"})
        assert r.status_code == 200
        assert "message" in r.json()

    def test_invalid_email_format_rejected(self):
        r = client.post(self.URL, json={"email": "not-an-email"})
        assert r.status_code == 422

    def test_missing_email_rejected(self):
        r = client.post(self.URL, json={})
        assert r.status_code == 422

    def test_production_does_not_log_token(self, caplog):
        """In production with RESET_TOKEN_LOG unset, the reset URL must not appear in logs."""
        import logging
        raw_token = _fake_token()
        with (
            patch.dict(os.environ, {"RICO_ENV": "production"}, clear=False),
            patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER),
            patch("src.repositories.password_reset_repo.create_reset_token", return_value=raw_token),
            caplog.at_level(logging.INFO),
        ):
            # Remove RESET_TOKEN_LOG if present
            os.environ.pop("RESET_TOKEN_LOG", None)
            client.post(self.URL, json={"email": "alice@rico.ai"})
        assert raw_token not in caplog.text

    def test_dev_logs_reset_url(self, caplog):
        """In non-production, the reset URL should appear in logs."""
        import logging
        raw_token = _fake_token()
        with (
            patch.dict(os.environ, {"RICO_ENV": "development"}, clear=False),
            patch("src.repositories.users_repo.get_user_by_email", return_value=_DB_USER),
            patch("src.repositories.password_reset_repo.create_reset_token", return_value=raw_token),
            caplog.at_level(logging.INFO),
        ):
            client.post(self.URL, json={"email": "alice@rico.ai"})
        assert raw_token in caplog.text


# ── POST /reset-password ──────────────────────────────────────────────────────

class TestResetPassword:
    URL = "/api/v1/auth/reset-password"

    def test_valid_token_updates_password(self):
        with (
            patch("src.repositories.password_reset_repo.consume_reset_token", return_value="alice@rico.ai"),
            patch("src.repositories.users_repo.update_password", return_value=True),
        ):
            r = client.post(self.URL, json={"token": _fake_token(), "new_password": "NewPass123!"})
        assert r.status_code == 200
        assert "updated" in r.json()["message"].lower() or "password" in r.json()["message"].lower()

    def test_invalid_token_returns_400(self):
        with patch("src.repositories.password_reset_repo.consume_reset_token", return_value=None):
            r = client.post(self.URL, json={"token": "bad-token", "new_password": "NewPass123!"})
        assert r.status_code == 400
        assert "invalid" in r.json()["detail"].lower() or "expired" in r.json()["detail"].lower()

    def test_expired_token_returns_400(self):
        """consume_reset_token returns None for expired tokens — endpoint must 400."""
        with patch("src.repositories.password_reset_repo.consume_reset_token", return_value=None):
            r = client.post(self.URL, json={"token": _fake_token(), "new_password": "NewPass123!"})
        assert r.status_code == 400

    def test_used_token_returns_400(self):
        """consume_reset_token returns None for already-used tokens."""
        with patch("src.repositories.password_reset_repo.consume_reset_token", return_value=None):
            r = client.post(self.URL, json={"token": _fake_token(), "new_password": "NewPass123!"})
        assert r.status_code == 400

    def test_token_is_consumed_on_success(self):
        """Verify consume_reset_token is called (token is single-use at repo level)."""
        with (
            patch("src.repositories.password_reset_repo.consume_reset_token", return_value="alice@rico.ai") as mock_consume,
            patch("src.repositories.users_repo.update_password", return_value=True),
        ):
            token = _fake_token()
            client.post(self.URL, json={"token": token, "new_password": "NewPass123!"})
        mock_consume.assert_called_once_with(token)

    def test_password_too_short_rejected(self):
        r = client.post(self.URL, json={"token": _fake_token(), "new_password": "short"})
        assert r.status_code == 422

    def test_password_too_long_rejected(self):
        r = client.post(self.URL, json={"token": _fake_token(), "new_password": "x" * 129})
        assert r.status_code == 422

    def test_missing_token_rejected(self):
        r = client.post(self.URL, json={"new_password": "NewPass123!"})
        assert r.status_code == 422

    def test_missing_password_rejected(self):
        r = client.post(self.URL, json={"token": _fake_token()})
        assert r.status_code == 422

    def test_db_update_failure_returns_503(self):
        with (
            patch("src.repositories.password_reset_repo.consume_reset_token", return_value="alice@rico.ai"),
            patch("src.repositories.users_repo.update_password", return_value=False),
        ):
            r = client.post(self.URL, json={"token": _fake_token(), "new_password": "NewPass123!"})
        assert r.status_code == 503
