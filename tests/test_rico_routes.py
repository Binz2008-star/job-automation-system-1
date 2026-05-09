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

    def test_chat_message_over_4096_chars_returns_422(self, client):
        r = client.post("/api/v1/rico/chat", json={"user_id": "user-1", "message": "A" * 4097})
        assert r.status_code == 422

    def test_chat_message_exactly_4096_chars_allowed(self, client):
        with patch("src.services.chat_service.send_message", return_value=_CHAT_RESPONSE):
            r = client.post("/api/v1/rico/chat", json={"user_id": "user-1", "message": "A" * 4096})
        assert r.status_code == 200


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

    def test_upload_cv_non_pdf_returns_422(self, client):
        r = client.post(
            "/api/v1/rico/upload-cv?user_id=user-1",
            files={"file": ("resume.pdf", io.BytesIO(b"This is not a PDF"), "application/pdf")},
        )
        assert r.status_code == 422

    def test_upload_cv_empty_file_returns_422(self, client):
        r = client.post(
            "/api/v1/rico/upload-cv?user_id=user-1",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert r.status_code == 422

    def test_upload_cv_exe_disguised_as_pdf_returns_422(self, client):
        exe_header = b"MZ\x90\x00" + b"\x00" * 60
        r = client.post(
            "/api/v1/rico/upload-cv?user_id=user-1",
            files={"file": ("malware.pdf", io.BytesIO(exe_header), "application/pdf")},
        )
        assert r.status_code == 422

    def test_upload_cv_path_traversal_filename_sanitised(self, client):
        with patch("src.services.chat_service.parse_cv", return_value=_CV_PARSED):
            r = client.post(
                "/api/v1/rico/upload-cv?user_id=user-1",
                files={"file": ("../../etc/passwd", io.BytesIO(b"%PDF-1.4 ok"), "application/pdf")},
            )
        assert r.status_code == 200
        assert "/" not in r.json()["filename"]
        assert ".." not in r.json()["filename"]

    def test_upload_cv_xss_filename_sanitised(self, client):
        with patch("src.services.chat_service.parse_cv", return_value=_CV_PARSED):
            r = client.post(
                "/api/v1/rico/upload-cv?user_id=user-1",
                files={"file": ('<script>alert(1)</script>.pdf', io.BytesIO(b"%PDF-1.4 ok"), "application/pdf")},
            )
        assert r.status_code == 200
        assert "<" not in r.json()["filename"]
        assert ">" not in r.json()["filename"]


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
        # Must include user data so the service doesn't short-circuit before delegating.
        payload = {"pretty": {"email": "test@example.com", "full_name": "Test User"}}
        with patch("src.rico_jotform_webhook.handle_jotform_submission", return_value=_JOTFORM_RESPONSE):
            result = handle_jotform_submission(payload)
        assert result == _JOTFORM_RESPONSE


# ═══════════════════════════════════════════════════════════════════════════════
# Regression: Jotform webhook robustness
# Covers the production 500 caused by empty/minimal Agent test payloads and
# raw Jotform field labels not matching the snake_case keys Rico expects.
# ═══════════════════════════════════════════════════════════════════════════════

class TestJotformWebhookRobustness:
    """Regression suite for Jotform 500 bug (rico-job-automation-api)."""

    # ── HTTP endpoint (via TestClient) ────────────────────────────────────────

    def test_agent_test_payload_returns_200(self, client):
        """Minimal Jotform Agent 'Send API Request' test payload must not 500."""
        r = client.post(
            "/api/v1/rico/webhooks/jotform",
            json={"formID": "261277622782059", "consent": "yes"},
        )
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"

    def test_agent_test_payload_returns_accepted(self, client):
        r = client.post(
            "/api/v1/rico/webhooks/jotform",
            json={"formID": "261277622782059", "consent": "yes"},
        )
        body = r.json()
        assert body["status"] == "accepted"
        assert "message" in body

    def test_empty_payload_returns_200(self, client):
        r = client.post("/api/v1/rico/webhooks/jotform", json={})
        assert r.status_code == 200

    def test_empty_payload_returns_accepted(self, client):
        r = client.post("/api/v1/rico/webhooks/jotform", json={})
        body = r.json()
        assert body["status"] == "accepted"

    def test_raw_jotform_field_names_reach_rico_handler(self, client):
        """Raw Jotform labels ('Full Name', 'Email') must be normalised and delegated."""
        payload = {
            "Full Name": "Robin Edwan",
            "Email": "robin@example.com",
            "Telegram Username": "@robin",
            "Target Job Titles": "HSE Manager",
        }
        with patch("src.rico_jotform_webhook.handle_jotform_submission", return_value=_JOTFORM_RESPONSE):
            r = client.post("/api/v1/rico/webhooks/jotform", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_pretty_key_payload_reaches_rico_handler(self, client):
        """Payload already using 'pretty' dict must be passed through unchanged."""
        payload = {
            "pretty": {
                "full_name": "Robin Edwan",
                "email": "robin@example.com",
            }
        }
        with patch("src.rico_jotform_webhook.handle_jotform_submission", return_value=_JOTFORM_RESPONSE):
            r = client.post("/api/v1/rico/webhooks/jotform", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_db_error_returns_200_not_500(self, client):
        """Even when the DB write fails, the router must return 200."""
        payload = {"pretty": {"email": "x@example.com"}}
        with patch(
            "src.rico_jotform_webhook.handle_jotform_submission",
            side_effect=RuntimeError("RicoDB unavailable: DATABASE_URL or psycopg2 missing"),
        ):
            r = client.post("/api/v1/rico/webhooks/jotform", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "accepted"

    def test_invalid_json_returns_200(self, client):
        r = client.post(
            "/api/v1/rico/webhooks/jotform",
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    # ── Service-layer unit tests (no HTTP) ────────────────────────────────────

    def test_normalize_strips_non_profile_keys(self):
        from src.services.chat_service import _normalize_jotform_payload
        out = _normalize_jotform_payload({"formID": "123", "consent": "yes"})
        assert "formID" in out
        assert "consent" in out

    def test_normalize_maps_full_name(self):
        from src.services.chat_service import _normalize_jotform_payload
        out = _normalize_jotform_payload({"Full Name": "Robin"})
        assert out.get("full_name") == "Robin"
        assert "Full Name" not in out

    def test_normalize_maps_email(self):
        from src.services.chat_service import _normalize_jotform_payload
        out = _normalize_jotform_payload({"Email": "a@b.com"})
        assert out.get("email") == "a@b.com"

    def test_normalize_maps_target_job_titles(self):
        from src.services.chat_service import _normalize_jotform_payload
        out = _normalize_jotform_payload({"Target Job Titles": "HSE Manager"})
        assert out.get("target_roles") == "HSE Manager"

    def test_normalize_passthrough_on_pretty_key(self):
        from src.services.chat_service import _normalize_jotform_payload
        payload = {"pretty": {"email": "x@y.com"}}
        assert _normalize_jotform_payload(payload) is payload

    def test_has_user_data_false_for_agent_test_payload(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({"formID": "261277622782059", "consent": "yes"}) is False

    def test_has_user_data_true_for_email(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({"email": "a@b.com"}) is True

    def test_has_user_data_true_via_pretty_key(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({"pretty": {"full_name": "Robin"}}) is True

    def test_service_short_circuits_empty_payload(self):
        from src.services.chat_service import handle_jotform_submission
        result = handle_jotform_submission({})
        assert result["status"] == "accepted"
        assert "no profile fields" in result["message"]

    def test_service_short_circuits_agent_test_payload(self):
        from src.services.chat_service import handle_jotform_submission
        result = handle_jotform_submission({"formID": "261277622782059", "consent": "yes"})
        assert result["status"] == "accepted"

    def test_service_returns_accepted_on_db_error(self):
        from src.services.chat_service import handle_jotform_submission
        payload = {"pretty": {"email": "x@example.com"}}
        with patch(
            "src.rico_jotform_webhook.handle_jotform_submission",
            side_effect=RuntimeError("DB down"),
        ):
            result = handle_jotform_submission(payload)
        assert result["status"] == "accepted"
        assert "pending" in result["message"]
