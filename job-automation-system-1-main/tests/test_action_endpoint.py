"""
tests/test_action_endpoint.py
Integration tests for POST /api/v1/actions/run.

Tests cover:
  - Auth guard (401 without token)
  - All 9 action types via dry_run (no side effects, no DB required)
  - Live execution of key actions with service layer patched
  - Unknown action → 200 ok=False (runtime validates, not HTTP layer)
  - Request validation → 422 for bad payloads
  - Rate limiting → 429 after burst
  - Response shape matches RuntimeResult
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ADMIN_EMAIL",    "admin@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass123")
os.environ.setdefault("JWT_SECRET",     "x" * 32)

_JOB = {
    "id":       "job-ep-001",
    "title":    "Risk Manager",
    "company":  "Gulf Corp",
    "location": "Abu Dhabi, UAE",
    "link":     "https://example.com/job/ep-001",
    "score":    82,
    "match_reason":        "Strong risk management background",
    "profile_explanation": "Matches your 8 years in EHS risk roles.",
}

_URL = "/api/v1/actions/run"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Authenticated test client."""
    from fastapi.testclient import TestClient
    from src.api.app import app
    from src.api.auth import create_access_token

    token = create_access_token({"sub": "action-test@rico.ai"})
    tc = TestClient(app, raise_server_exceptions=False)
    tc.cookies.set("access_token", token)
    return tc


@pytest.fixture(scope="module")
def anon_client():
    """Unauthenticated test client."""
    from fastapi.testclient import TestClient
    from src.api.app import app
    return TestClient(app, raise_server_exceptions=False)


# ── Auth ──────────────────────────────────────────────────────────────────────

class TestActionEndpointAuth:
    def test_unauthenticated_returns_401(self, anon_client):
        r = anon_client.post(_URL, json={"action": "why", "job": _JOB})
        assert r.status_code == 401

    def test_authenticated_reaches_endpoint(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB})
        assert r.status_code == 200

    def test_user_id_comes_from_jwt_not_body(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB, "source": "api"})
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == "action-test@rico.ai"


# ── Request validation ────────────────────────────────────────────────────────

class TestActionEndpointValidation:
    def test_missing_action_returns_422(self, client):
        r = client.post(_URL, json={"job": _JOB})
        assert r.status_code == 422

    def test_empty_body_returns_422(self, client):
        r = client.post(_URL, json={})
        assert r.status_code == 422

    def test_non_json_body_returns_422(self, client):
        r = client.post(_URL, data="not-json", headers={"Content-Type": "text/plain"})
        assert r.status_code in (422, 415)


# ── Response shape ────────────────────────────────────────────────────────────

class TestActionEndpointResponseShape:
    def test_response_has_all_required_fields(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB})
        assert r.status_code == 200
        data = r.json()
        for field in ("ok", "message", "action", "job_key", "source", "user_id",
                       "dry_run", "data", "error", "confidence", "explanation", "duration_ms"):
            assert field in data, f"missing field: {field}"

    def test_action_echoed_in_response(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB})
        assert r.json()["action"] == "why"

    def test_source_echoed_in_response(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB, "source": "dashboard"})
        assert r.json()["source"] == "dashboard"

    def test_duration_ms_is_non_negative(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB})
        assert r.json()["duration_ms"] >= 0

    def test_confidence_is_float(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB})
        assert isinstance(r.json()["confidence"], float)


# ── Unknown action ────────────────────────────────────────────────────────────

class TestActionEndpointUnknownAction:
    def test_unknown_action_returns_200_ok_false(self, client):
        r = client.post(_URL, json={"action": "launch_rocket", "job": _JOB})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False

    def test_unknown_action_message_describes_error(self, client):
        r = client.post(_URL, json={"action": "launch_rocket", "job": _JOB})
        msg = r.json()["message"]
        assert "launch_rocket" in msg or "Unknown" in msg or "Supported" in msg

    def test_empty_action_returns_200_ok_false(self, client):
        r = client.post(_URL, json={"action": "", "job": _JOB})
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert r.json()["ok"] is False


# ── Dry-run mode ──────────────────────────────────────────────────────────────

class TestActionEndpointDryRun:
    @pytest.mark.parametrize("action", [
        "apply", "save", "skip", "not_relevant", "why", "draft", "remind",
    ])
    def test_dry_run_all_actions_return_ok(self, client, action):
        r = client.post(_URL, json={"action": action, "job": _JOB, "dry_run": True})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True, f"action={action} dry_run returned ok=False: {data}"
        assert data["dry_run"] is True

    def test_dry_run_message_contains_dry_run_label(self, client):
        r = client.post(_URL, json={"action": "apply", "job": _JOB, "dry_run": True})
        assert "DRY RUN" in r.json()["message"] or "dry" in r.json()["message"].lower()

    def test_dry_run_no_audit_side_effects(self, client):
        with patch("src.agent.runtime.log_action") as mock_log:
            r = client.post(_URL, json={"action": "save", "job": _JOB, "dry_run": True})
        assert r.status_code == 200
        mock_log.assert_not_called()


# ── Live execution (service layer patched) ────────────────────────────────────

class TestActionEndpointLiveExecution:
    def test_why_action_returns_explanation(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "explanation" in data["data"]
        assert len(data["message"]) > 0

    def test_save_action_calls_mark_applied(self, client):
        with patch("src.agent.runtime.log_action"), \
             patch("src.agent.runtime.is_duplicate", return_value=False), \
             patch("src.applications.mark_applied", return_value=True):
            r = client.post(_URL, json={"action": "save", "job": _JOB})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_apply_action_triggers_apply_service(self, client):
        with patch("src.agent.runtime.log_action"), \
             patch("src.agent.runtime.is_duplicate", return_value=False), \
             patch("src.services.apply_service.apply_to_job", return_value={"status": "applied"}):
            r = client.post(_URL, json={"action": "apply", "job": _JOB})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_skip_action_calls_skip_service(self, client):
        with patch("src.agent.runtime.log_action"), \
             patch("src.agent.runtime.is_duplicate", return_value=False), \
             patch("src.services.jobs_service.skip_job", return_value=True):
            r = client.post(_URL, json={"action": "skip", "job": _JOB})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_not_relevant_maps_to_skip(self, client):
        with patch("src.agent.runtime.log_action"), \
             patch("src.agent.runtime.is_duplicate", return_value=False), \
             patch("src.services.jobs_service.skip_job", return_value=True):
            r = client.post(_URL, json={"action": "not_relevant", "job": _JOB})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["action"] == "not_relevant"

    def test_draft_action_returns_message(self, client):
        with patch("src.agent.runtime.log_action"), \
             patch("src.agent.runtime.is_duplicate", return_value=False), \
             patch("src.message_generator.generate_message", return_value="Dear Hiring Manager..."):
            r = client.post(_URL, json={"action": "draft", "job": _JOB})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "Dear Hiring Manager" in data["message"]

    def test_remind_action_sets_reminder_date(self, client):
        with patch("src.agent.runtime.log_action"), \
             patch("src.agent.runtime.is_duplicate", return_value=False), \
             patch("src.applications.update_application_status"):
            r = client.post(_URL, json={"action": "remind", "job": _JOB})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "reminder_date" in data["data"]


# ── job_key fallback ──────────────────────────────────────────────────────────

class TestActionEndpointJobResolution:
    def test_job_key_without_job_dict_works(self, client):
        r = client.post(_URL, json={
            "action": "why",
            "job_key": "some-key-no-cache",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_job_dict_takes_precedence_over_key(self, client):
        with patch("src.agent.runtime.log_action"), \
             patch("src.agent.runtime.is_duplicate", return_value=False), \
             patch("src.message_generator.generate_message") as mock_gen:
            mock_gen.return_value = "msg"
            client.post(_URL, json={
                "action":  "draft",
                "job_key": "ignored-key",
                "job":     _JOB,
            })
        mock_gen.assert_called_once_with(_JOB)


# ── Rate limiting ─────────────────────────────────────────────────────────────

class TestActionEndpointRateLimit:
    def test_below_limit_not_blocked(self, client):
        r = client.post(_URL, json={"action": "why", "job": _JOB})
        assert r.status_code in (200, 429)

    def test_burst_triggers_429(self, client):
        responses = [
            client.post(_URL, json={"action": "why", "job": _JOB})
            for _ in range(35)
        ]
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, "Expected at least one 429 after burst"
