"""Security tests for webhook secret validation in production.

Tests verify that webhooks fail closed in production when secrets are missing.
"""
import hashlib
import hmac
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    """Test client for API endpoints."""
    from fastapi.testclient import TestClient
    from src.api.app import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_client():
    """Authenticated client with a valid JWT cookie."""
    from fastapi.testclient import TestClient
    from src.api.app import app
    from src.api.auth import create_access_token
    token = create_access_token({"sub": "test@example.com", "role": "user"})
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies.set("access_token", token)
    return tc


def _github_sig(body: bytes, secret: str) -> str:
    """Generate GitHub webhook signature."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestJotformWebhookSecurity:
    """Test Jotform webhook secret validation in production."""

    def test_production_jotform_without_secret_returns_503(self, client):
        """In production, missing JOTFORM_WEBHOOK_SECRET should return 503."""
        with patch.dict(os.environ, {"APP_ENV": "production"}), \
             patch.dict(os.environ, {}, clear=False):
            # Remove JOTFORM_WEBHOOK_SECRET if it exists
            original = os.environ.pop("JOTFORM_WEBHOOK_SECRET", None)
            try:
                r = client.post("/api/v1/rico/webhooks/jotform", json={"email": "test@example.com"})
                assert r.status_code == 503
                assert "Webhook not configured" in r.json()["detail"]
            finally:
                if original:
                    os.environ["JOTFORM_WEBHOOK_SECRET"] = original

    def test_production_jotform_with_wrong_secret_returns_403(self, client):
        """In production, wrong secret should return 403."""
        with patch.dict(os.environ, {"APP_ENV": "production", "JOTFORM_WEBHOOK_SECRET": "correct-secret"}):
            r = client.post(
                "/api/v1/rico/webhooks/jotform",
                json={"email": "test@example.com"},
                headers={"X-Jotform-Signature": "wrong-secret"}
            )
            assert r.status_code == 403
            assert "Invalid or missing webhook secret" in r.json()["detail"]

    def test_production_jotform_with_correct_secret_succeeds(self, client):
        """In production, correct secret should allow request."""
        with patch.dict(os.environ, {"APP_ENV": "production", "JOTFORM_WEBHOOK_SECRET": "mysecret"}), \
             patch("src.services.chat_service.handle_jotform_submission", return_value={"status": "ok"}):
            r = client.post(
                "/api/v1/rico/webhooks/jotform",
                json={"email": "test@example.com"},
                headers={"X-Jotform-Signature": "mysecret"}
            )
            assert r.status_code == 200

    def test_development_jotform_without_secret_allowed(self, client):
        """In development, missing secret should be allowed with warning."""
        with patch.dict(os.environ, {"APP_ENV": "development"}), \
             patch.dict(os.environ, {}, clear=False):
            # Remove JOTFORM_WEBHOOK_SECRET if it exists
            original = os.environ.pop("JOTFORM_WEBHOOK_SECRET", None)
            try:
                with patch("src.services.chat_service.handle_jotform_submission", return_value={"status": "ok"}):
                    r = client.post("/api/v1/rico/webhooks/jotform", json={"email": "test@example.com"})
                    assert r.status_code == 200
            finally:
                if original:
                    os.environ["JOTFORM_WEBHOOK_SECRET"] = original


class TestGitHubWebhookSecurity:
    """Test GitHub webhook secret validation in production."""

    def test_production_github_without_secret_returns_503(self, client):
        """In production, missing GITHUB_WEBHOOK_SECRET should return 503."""
        body = b'{"zen": "test"}'
        with patch.dict(os.environ, {"APP_ENV": "production"}), \
             patch.dict(os.environ, {}, clear=False):
            # Remove GITHUB_WEBHOOK_SECRET if it exists
            original = os.environ.pop("GITHUB_WEBHOOK_SECRET", None)
            try:
                r = client.post(
                    "/api/v1/rico/webhooks/github",
                    content=body,
                    headers={"X-GitHub-Event": "ping", "Content-Type": "application/json"}
                )
                assert r.status_code == 503
                assert "Webhook not configured" in r.json()["detail"]
            finally:
                if original:
                    os.environ["GITHUB_WEBHOOK_SECRET"] = original

    def test_production_github_with_wrong_signature_returns_403(self, client):
        """In production, wrong signature should return 403."""
        body = b'{"zen": "test"}'
        with patch.dict(os.environ, {"APP_ENV": "production", "GITHUB_WEBHOOK_SECRET": "correct-secret"}):
            r = client.post(
                "/api/v1/rico/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": "sha256=wronghash",
                    "Content-Type": "application/json"
                }
            )
            assert r.status_code == 403
            assert "Invalid webhook signature" in r.json()["detail"]

    def test_production_github_with_correct_signature_succeeds(self, client):
        """In production, correct signature should allow request."""
        body = b'{"zen": "test"}'
        secret = "mysecret"
        sig = _github_sig(body, secret)
        with patch.dict(os.environ, {"APP_ENV": "production", "GITHUB_WEBHOOK_SECRET": secret}), \
             patch("src.services.chat_service.handle_github_event", return_value={"status": "ok"}):
            r = client.post(
                "/api/v1/rico/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json"
                }
            )
            assert r.status_code == 200

    def test_development_github_without_secret_allowed(self, client):
        """In development, missing secret should be allowed with warning."""
        body = b'{"zen": "test"}'
        with patch.dict(os.environ, {"APP_ENV": "development"}), \
             patch.dict(os.environ, {}, clear=False):
            # Remove GITHUB_WEBHOOK_SECRET if it exists
            original = os.environ.pop("GITHUB_WEBHOOK_SECRET", None)
            try:
                with patch("src.services.chat_service.handle_github_event", return_value={"status": "ok"}):
                    r = client.post(
                        "/api/v1/rico/webhooks/github",
                        content=body,
                        headers={"X-GitHub-Event": "ping", "Content-Type": "application/json"}
                    )
                    assert r.status_code == 200
            finally:
                if original:
                    os.environ["GITHUB_WEBHOOK_SECRET"] = original


class TestAIProviderHealthSecurity:
    """Test AI provider health endpoint security."""

    def test_ai_provider_health_requires_auth(self, client):
        """AI provider health endpoint should require authentication."""
        r = client.get("/api/v1/rico/health/ai-provider")
        assert r.status_code == 401

    def test_ai_provider_health_succeeds_with_auth(self, auth_client):
        """AI provider health endpoint should succeed with valid auth."""
        with patch("src.rico_openai_agent.RicoOpenAIAgent") as mock_agent_class, \
             patch("src.rico_env.get_ai_provider", return_value="deepseek"):
            mock_agent = mock_agent_class.return_value
            mock_agent.provider_available = True
            mock_agent.openai_available = False
            mock_agent.hf_available = False

            r = auth_client.get("/api/v1/rico/health/ai-provider")
            assert r.status_code == 200
            data = r.json()
            assert "active_provider" in data
