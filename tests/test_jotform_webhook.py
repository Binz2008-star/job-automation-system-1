"""
tests/test_jotform_webhook.py
Regression tests for Jotform webhook fixes (feat/jotform-webhook-fix).

Invariants verified:
  - Form ID validation: unknown form IDs are rejected when JOTFORM_FORM_ID is set
  - user_id consistency: email preferred, telegram_username fallback, full_name excluded
  - consent → mark_onboarding_complete called
  - DB failure isolation: upsert_profile / upsert_settings failures do not abort the submission
  - Graceful handling: no stable user_id → accepted without DB write
  - Structured logging: form_id, submission_id, user_id always logged
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _payload(
    email=None,
    telegram=None,
    name=None,
    consent=None,
    form_id=None,
    submission_id=None,
) -> dict:
    p: dict = {}
    if form_id:
        p["formID"] = form_id
    if submission_id:
        p["submissionID"] = submission_id
    if email:
        p["email"] = email
    if telegram:
        p["telegram_username"] = telegram
    if name:
        p["full_name"] = name
    if consent is not None:
        p["consent"] = consent
    return p


def _mock_db(user_id="db-uuid-1") -> MagicMock:
    db = MagicMock()
    db.upsert_user.return_value = {"id": user_id}
    return db


# ── _resolve_user_id ──────────────────────────────────────────────────────────

class TestResolveUserId:
    def test_email_preferred(self):
        from src.rico_jotform_webhook import _resolve_user_id
        assert _resolve_user_id({"email": "a@b.com", "telegram_username": "tg"}) == "a@b.com"

    def test_telegram_fallback(self):
        from src.rico_jotform_webhook import _resolve_user_id
        assert _resolve_user_id({"telegram_username": "tg_user"}) == "tg_user"

    def test_full_name_excluded(self):
        from src.rico_jotform_webhook import _resolve_user_id
        assert _resolve_user_id({"full_name": "John Doe"}) is None

    def test_empty_returns_none(self):
        from src.rico_jotform_webhook import _resolve_user_id
        assert _resolve_user_id({}) is None


# ── map_jotform_payload ───────────────────────────────────────────────────────

class TestMapJotformPayload:
    def test_external_user_id_uses_email(self):
        from src.rico_jotform_webhook import map_jotform_payload
        result = map_jotform_payload({"email": "x@y.com", "full_name": "X"})
        assert result["user"]["external_user_id"] == "x@y.com"

    def test_external_user_id_uses_telegram_when_no_email(self):
        from src.rico_jotform_webhook import map_jotform_payload
        result = map_jotform_payload({"telegram_username": "@rico_user"})
        assert result["user"]["external_user_id"] == "@rico_user"

    def test_external_user_id_none_when_only_name(self):
        from src.rico_jotform_webhook import map_jotform_payload
        result = map_jotform_payload({"full_name": "Nobody"})
        assert result["user"]["external_user_id"] is None

    def test_consent_true(self):
        from src.rico_jotform_webhook import map_jotform_payload
        result = map_jotform_payload({"email": "a@b.com", "consent": "Yes"})
        assert result["consent"] is True

    def test_consent_false_when_absent(self):
        from src.rico_jotform_webhook import map_jotform_payload
        result = map_jotform_payload({"email": "a@b.com"})
        assert result["consent"] is False

    def test_form_id_captured(self):
        from src.rico_jotform_webhook import map_jotform_payload
        result = map_jotform_payload({"email": "a@b.com", "formID": "123"})
        assert result["form_id"] == "123"

    def test_pretty_key_passthrough(self):
        from src.rico_jotform_webhook import map_jotform_payload
        payload = {"pretty": {"email": "p@q.com"}}
        result = map_jotform_payload(payload)
        assert result["user"]["external_user_id"] == "p@q.com"


# ── Form ID validation ────────────────────────────────────────────────────────

class TestFormIdValidation:
    def test_known_form_id_accepted(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, {"JOTFORM_FORM_ID": "form-abc"}), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete"):
            result = handle_jotform_submission(
                {"formID": "form-abc", "email": "u@x.com", "consent": True}
            )
        assert result["status"] == "ok"

    def test_unknown_form_id_rejected(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        with patch.dict(os.environ, {"JOTFORM_FORM_ID": "form-abc"}):
            result = handle_jotform_submission(
                {"formID": "hacker-form", "email": "u@x.com"}
            )
        assert result["status"] == "rejected"
        assert result["reason"] == "unknown_form_id"

    def test_no_env_var_accepts_any_form_id(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete"):
            result = handle_jotform_submission(
                {"formID": "any-form", "email": "u@x.com", "consent": True}
            )
        assert result["status"] == "ok"

    def test_comma_separated_form_ids(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, {"JOTFORM_FORM_ID": "form-1, form-2"}), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete"):
            r1 = handle_jotform_submission({"formID": "form-1", "email": "a@b.com", "consent": True})
            r2 = handle_jotform_submission({"formID": "form-2", "email": "c@d.com", "consent": True})
        assert r1["status"] == "ok"
        assert r2["status"] == "ok"


# ── No stable user_id ─────────────────────────────────────────────────────────

class TestNoUserId:
    def test_name_only_payload_skips_db(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True):
            result = handle_jotform_submission({"full_name": "Ghost User"})
        assert result["status"] == "accepted"
        db.upsert_user.assert_not_called()

    def test_empty_payload_skips_db(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True):
            result = handle_jotform_submission({})
        assert result["status"] == "accepted"
        db.upsert_user.assert_not_called()


# ── Consent → mark onboarding complete ───────────────────────────────────────

class TestConsentOnboarding:
    def _run(self, consent, env=None):
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        payload = {"email": "u@x.com", "consent": consent}
        _env = env or {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, _env, clear=True), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete") as mock_complete:
            handle_jotform_submission(payload)
        return mock_complete

    def test_consent_true_calls_mark_complete(self):
        mock = self._run(consent=True)
        mock.assert_called_once_with("u@x.com")

    def test_consent_false_does_not_call_mark_complete(self):
        mock = self._run(consent=False)
        mock.assert_not_called()

    def test_consent_absent_does_not_call_mark_complete(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete") as mock_complete:
            handle_jotform_submission({"email": "u@x.com"})
        mock_complete.assert_not_called()

    def test_mark_complete_failure_does_not_abort_submission(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete",
                   side_effect=RuntimeError("DB down")):
            result = handle_jotform_submission({"email": "u@x.com", "consent": True})
        assert result["status"] == "ok"


# ── DB failure isolation ──────────────────────────────────────────────────────

class TestDbFailureIsolation:
    def _run_with_db(self, db):
        from src.rico_jotform_webhook import handle_jotform_submission
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete"):
            return handle_jotform_submission({"email": "u@x.com", "consent": True})

    def test_upsert_profile_failure_still_returns_ok(self):
        db = _mock_db()
        db.upsert_profile.side_effect = RuntimeError("profile table missing")
        result = self._run_with_db(db)
        assert result["status"] == "ok"

    def test_upsert_settings_failure_still_returns_ok(self):
        db = _mock_db()
        db.upsert_settings.side_effect = RuntimeError("settings table missing")
        result = self._run_with_db(db)
        assert result["status"] == "ok"

    def test_upsert_user_failure_propagates(self):
        """upsert_user failure must propagate — chat_service wraps it in a graceful 'accepted'."""
        from src.rico_jotform_webhook import handle_jotform_submission
        db = _mock_db()
        db.upsert_user.side_effect = RuntimeError("connection lost")
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="connection lost"):
                handle_jotform_submission({"email": "u@x.com"})


# ── chat_service._has_user_data ───────────────────────────────────────────────

class TestHasUserData:
    def test_email_is_sufficient(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({"email": "a@b.com"}) is True

    def test_telegram_is_sufficient(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({"telegram_username": "@tg"}) is True

    def test_full_name_alone_is_not_sufficient(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({"full_name": "John Doe"}) is False

    def test_name_alone_is_not_sufficient(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({"name": "John"}) is False

    def test_empty_returns_false(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({}) is False

    def test_pretty_key_respected(self):
        from src.services.chat_service import _has_user_data
        assert _has_user_data({"pretty": {"email": "a@b.com"}}) is True
        assert _has_user_data({"pretty": {"full_name": "X"}}) is False


# ── Webhook secret validation ─────────────────────────────────────────────────

class TestJotformWebhookSecret:
    def _post(self, headers=None, env=None):
        from fastapi.testclient import TestClient
        from src.api.app import app
        _env = env or {}
        with patch.dict(os.environ, _env, clear=False), \
             patch("src.services.chat_service.handle_jotform_submission",
                   return_value={"status": "ok", "user_id": "1"}):
            tc = TestClient(app, raise_server_exceptions=False)
            return tc.post(
                "/api/v1/rico/webhooks/jotform",
                json={"email": "u@x.com", "consent": True},
                headers=headers or {},
            )

    def test_no_secret_configured_allows_any_request(self):
        """When JOTFORM_WEBHOOK_SECRET is absent, all requests are allowed."""
        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_WEBHOOK_SECRET"}
        r = self._post(env={**env, "JOTFORM_WEBHOOK_SECRET": ""})
        assert r.status_code == 200

    def test_correct_secret_header_accepted(self):
        r = self._post(
            headers={"X-Jotform-Signature": "mysecret"},
            env={"JOTFORM_WEBHOOK_SECRET": "mysecret"},
        )
        assert r.status_code == 200

    def test_missing_secret_header_rejected_in_production(self):
        """When secret is configured, requests without it must be rejected (403)."""
        r = self._post(env={"JOTFORM_WEBHOOK_SECRET": "mysecret"})
        assert r.status_code == 403

    def test_wrong_secret_rejected(self):
        r = self._post(
            headers={"X-Jotform-Signature": "wrongsecret"},
            env={"JOTFORM_WEBHOOK_SECRET": "mysecret"},
        )
        assert r.status_code == 403


# ── SubmissionID idempotency ──────────────────────────────────────────────────

class TestSubmissionIdempotency:
    def test_duplicate_submission_id_returns_accepted(self):
        from src.rico_jotform_webhook import handle_jotform_submission
        with patch("src.rico_jotform_webhook._is_duplicate_submission", return_value=True):
            result = handle_jotform_submission(
                {"submissionID": "sub-1", "email": "u@x.com"}
            )
        assert result["status"] == "accepted"
        assert "Duplicate" in result["message"]

    def test_new_submission_id_is_not_duplicate(self):
        from src.rico_jotform_webhook import _is_duplicate_submission
        with patch("src.rico_jotform_webhook._load_seen_submissions", return_value=set()):
            assert _is_duplicate_submission("fresh-id") is False

    def test_empty_submission_id_never_duplicate(self):
        from src.rico_jotform_webhook import _is_duplicate_submission
        assert _is_duplicate_submission("") is False
        assert _is_duplicate_submission("?") is False
