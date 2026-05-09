"""
tests/test_rico_routes.py
Smoke tests verifying Rico routes are mounted and reachable through the
layered API. Rico internals are fully mocked — no DB or Telegram tokens needed.
"""
from __future__ import annotations

import io
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("ADMIN_EMAIL", "rico-test@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "ricopass123")
os.environ.setdefault("JWT_SECRET", "ricosecret" + "x" * 21)

# ── Shared test client ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.api.app import app
    return TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

_CHAT_RESPONSE = {"type": "assistant", "message": "Hello from Rico"}
_CV_PARSED = {
    "text": "Sample CV text",
    "skills": ["hse"],
    "emails": ["test@example.com"],
    "phones": [],
    "years_experience_hint": 5.0,
    "certifications": ["nebosh"],
    "languages": ["english"],
}
_TELEGRAM_RESPONSE = {"chat_id": "12345", "reply": {"type": "assistant", "message": "Hi"}}
_JOTFORM_RESPONSE = {"status": "ok", "user_id": "42"}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Route existence — every route must return 2xx (not 404 / 405)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRicoChatRouteExists:
    def test_chat_route_returns_200(self, client):
        with patch("src.services.chat_service.send_message", return_value=_CHAT_RESPONSE):
            r = client.post(
                "/api/v1/rico/chat",
                json={"user_id": "user-1", "message": "Hello"},
            )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_chat_route_not_404(self, client):
        with patch("src.services.chat_service.send_message", return_value=_CHAT_RESPONSE):
            r = client.post(
                "/api/v1/rico/chat",
                json={"user_id": "user-1", "message": "Hello"},
            )
        assert r.status_code != 404, "Rico chat route is not mounted"

    def test_chat_response_body_passes_through(self, client):
        with patch("src.services.chat_service.send_message", return_value=_CHAT_RESPONSE):
            r = client.post(
                "/api/v1/rico/chat",
                json={"user_id": "user-2", "message": "Find me jobs"},
            )
        assert r.status_code == 200
        assert r.json()["message"] == "Hello from Rico"

    def test_chat_missing_user_id_returns_422(self, client):
        r = client.post("/api/v1/rico/chat", json={"message": "Hello"})
        assert r.status_code == 422

    def test_chat_missing_message_returns_422(self, client):
        r = client.post("/api/v1/rico/chat", json={"user_id": "user-1"})
        assert r.status_code == 422


class TestRicoCVUploadRouteExists:
    def test_upload_cv_route_returns_200(self, client):
        with patch("src.services.chat_service.parse_cv", return_value=_CV_PARSED):
            r = client.post(
                "/api/v1/rico/upload-cv?user_id=user-1",
                files={"file": ("cv.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_upload_cv_route_not_404(self, client):
        with patch("src.services.chat_service.parse_cv", return_value=_CV_PARSED):
            r = client.post(
                "/api/v1/rico/upload-cv?user_id=user-1",
                files={"file": ("cv.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            )
        assert r.status_code != 404, "Rico upload-cv route is not mounted"

    def test_upload_cv_response_contains_parsed_key(self, client):
        with patch("src.services.chat_service.parse_cv", return_value=_CV_PARSED):
            r = client.post(
                "/api/v1/rico/upload-cv?user_id=user-1",
                files={"file": ("resume.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            )
        assert r.status_code == 200
        body = r.json()
        assert "parsed" in body
        assert "user_id" in body
        assert body["user_id"] == "user-1"

    def test_upload_cv_missing_file_returns_422(self, client):
        r = client.post("/api/v1/rico/upload-cv?user_id=user-1")
        assert r.status_code == 422

    def test_upload_cv_missing_user_id_returns_422(self, client):
        r = client.post(
            "/api/v1/rico/upload-cv",
            files={"file": ("cv.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        )
        assert r.status_code == 422


class TestRicoTelegramWebhookRouteExists:
    def test_telegram_webhook_route_returns_200(self, client):
        update = {
            "message": {
                "chat": {"id": 12345},
                "from": {"id": 12345},
                "text": "Hello",
            }
        }
        with patch("src.services.chat_service.handle_telegram_update", return_value=_TELEGRAM_RESPONSE):
            r = client.post("/api/v1/rico/webhooks/telegram", json=update)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_telegram_webhook_route_not_404(self, client):
        with patch("src.services.chat_service.handle_telegram_update", return_value=_TELEGRAM_RESPONSE):
            r = client.post("/api/v1/rico/webhooks/telegram", json={})
        assert r.status_code != 404, "Rico Telegram webhook route is not mounted"

    def test_telegram_webhook_passes_update_to_service(self, client):
        update = {"message": {"chat": {"id": 99}, "text": "test"}}
        captured = {}

        def spy(u):
            captured["update"] = u
            return _TELEGRAM_RESPONSE

        with patch("src.services.chat_service.handle_telegram_update", side_effect=spy):
            r = client.post("/api/v1/rico/webhooks/telegram", json=update)
        assert r.status_code == 200
        assert captured["update"] == update


class TestRicoJotformWebhookRouteExists:
    def test_jotform_webhook_route_returns_200(self, client):
        payload = {"pretty": {"email": "test@example.com", "full_name": "Test User"}}
        with patch("src.services.chat_service.handle_jotform_submission", return_value=_JOTFORM_RESPONSE):
            r = client.post("/api/v1/rico/webhooks/jotform", json=payload)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_jotform_webhook_route_not_404(self, client):
        with patch("src.services.chat_service.handle_jotform_submission", return_value=_JOTFORM_RESPONSE):
            r = client.post("/api/v1/rico/webhooks/jotform", json={})
        assert r.status_code != 404, "Rico Jotform webhook route is not mounted"

    def test_jotform_webhook_response_has_status(self, client):
        payload = {"pretty": {"email": "a@b.com"}}
        with patch("src.services.chat_service.handle_jotform_submission", return_value=_JOTFORM_RESPONSE):
            r = client.post("/api/v1/rico/webhooks/jotform", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["user_id"] == "42"

    def test_jotform_webhook_passes_payload_to_service(self, client):
        payload = {"pretty": {"full_name": "Jane"}}
        captured = {}

        def spy(p):
            captured["payload"] = p
            return _JOTFORM_RESPONSE

        with patch("src.services.chat_service.handle_jotform_submission", side_effect=spy):
            r = client.post("/api/v1/rico/webhooks/jotform", json=payload)
        assert r.status_code == 200
        assert captured["payload"] == payload


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Service-layer unit tests (no HTTP)
# ═══════════════════════════════════════════════════════════════════════════════

class TestChatService:
    def test_send_message_delegates_to_rico_chat_api(self):
        from src.services.chat_service import send_message
        mock_api = type("API", (), {"process_message": lambda self, user_id, message: _CHAT_RESPONSE})()
        with patch("src.rico_chat_api.RicoChatAPI", return_value=mock_api):
            result = send_message("u1", "hi")
        assert result == _CHAT_RESPONSE

    def test_parse_cv_delegates_to_cv_parser(self):
        from src.services.chat_service import parse_cv
        mock_parsed = type("P", (), {"to_dict": lambda self: _CV_PARSED})()
        mock_parser = type("Parser", (), {"parse_bytes": lambda self, d, filename: mock_parsed})()
        with patch("src.cv_parser.CVParser", return_value=mock_parser):
            result = parse_cv(b"fake pdf data", filename="cv.pdf")
        assert result == _CV_PARSED

    def test_handle_telegram_update_delegates(self):
        from src.services.chat_service import handle_telegram_update
        update = {"message": {"text": "hello"}}
        with patch("src.rico_telegram_webhook.process_telegram_update", return_value=_TELEGRAM_RESPONSE):
            result = handle_telegram_update(update)
        assert result == _TELEGRAM_RESPONSE

    def test_handle_jotform_submission_delegates(self):
        from src.services.chat_service import handle_jotform_submission
        payload = {"pretty": {}}
        with patch("src.rico_jotform_webhook.handle_jotform_submission", return_value=_JOTFORM_RESPONSE):
            result = handle_jotform_submission(payload)
        assert result == _JOTFORM_RESPONSE
