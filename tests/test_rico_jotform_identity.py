"""
tests/test_rico_jotform_identity.py
Tests for Jotform webhook identity resolution integration.

Test cases:
- exact email candidate → merge and writes existing external_user_id
- exact phone candidate → merge
- exact Telegram candidate → merge
- conflict on strong match → pending_identity_confirmation
- weak/empty signal → existing missing-user or ignored behavior
- duplicate submission → still returns duplicate before identity lookup
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _payload(
    email=None,
    phone=None,
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
    if phone:
        p["phone"] = phone
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
    db.register_webhook_event.return_value = True
    return db


def _mock_identity_resolution(action="merge", matched_user_id=None, confidence=1.0):
    """Create a mock IdentityResolution."""
    from src.services.identity_flow_mapper import IdentityResolution
    return IdentityResolution(
        action=action,
        confidence=confidence,
        matched_user_id=matched_user_id,
        reasons=["test reason"],
        conflicts={},
        missing_fields=[],
    )


# ── Exact email candidate → merge ─────────────────────────────────────────────

class TestExactEmailCandidate:
    def test_merge_on_exact_email_match(self):
        """When an exact email match is found, should merge into existing profile."""
        from src.rico_jotform_webhook import handle_jotform_submission
        from src.services.profile_context_resolver import ProfileContext

        db = _mock_db()
        candidate = ProfileContext(
            user_id="existing-user-123",
            name="Existing User",
            email="user@example.com",
            phone=None,
            telegram_username=None,
            target_roles=["Software Engineer"],
            preferred_cities=["Dubai"],
            skills=["Python"],
            industries=[],
            years_experience=5,
            salary_expectation_aed=15000,
            current_role="Developer",
            visa_status=None,
            notice_period=None,
        )

        resolution = _mock_identity_resolution(action="merge", matched_user_id="existing-user-123", confidence=1.0)

        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.rico_jotform_webhook.find_identity_candidates", return_value=[candidate]), \
             patch("src.rico_jotform_webhook.map_identity_flow", return_value=resolution), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete"):
            result = handle_jotform_submission(
                {"submissionID": "sub-email-1", "email": "user@example.com", "consent": True}
            )

        assert result["status"] == "ok"
        # Verify that upsert_user was called
        db.upsert_user.assert_called_once()


# ── Exact phone candidate → merge ───────────────────────────────────────────────

class TestExactPhoneCandidate:
    def test_merge_on_exact_phone_match(self):
        """When an exact phone match is found, should merge into existing profile."""
        from src.rico_jotform_webhook import handle_jotform_submission
        from src.services.profile_context_resolver import ProfileContext

        db = _mock_db()
        candidate = ProfileContext(
            user_id="existing-user-456",
            name="Phone User",
            email=None,
            phone="+971501234567",
            telegram_username=None,
            target_roles=["Data Analyst"],
            preferred_cities=["Abu Dhabi"],
            skills=["SQL"],
            industries=[],
            years_experience=3,
            salary_expectation_aed=12000,
            current_role="Analyst",
            visa_status=None,
            notice_period=None,
        )

        resolution = _mock_identity_resolution(action="merge", matched_user_id="existing-user-456", confidence=1.0)

        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.rico_jotform_webhook.find_identity_candidates", return_value=[candidate]), \
             patch("src.rico_jotform_webhook.map_identity_flow", return_value=resolution), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete"):
            result = handle_jotform_submission(
                {"submissionID": "sub-phone-1", "phone": "+971501234567", "consent": True}
            )

        assert result["status"] == "ok"
        db.upsert_user.assert_called_once()


# ── Exact Telegram candidate → merge ───────────────────────────────────────────

class TestExactTelegramCandidate:
    def test_merge_on_exact_telegram_match(self):
        """When an exact telegram match is found, should merge into existing profile."""
        from src.rico_jotform_webhook import handle_jotform_submission
        from src.services.profile_context_resolver import ProfileContext

        db = _mock_db()
        candidate = ProfileContext(
            user_id="existing-user-789",
            name="Telegram User",
            email=None,
            phone=None,
            telegram_username="@telegram_user",
            target_roles=["Product Manager"],
            preferred_cities=["Dubai"],
            skills=["Agile"],
            industries=[],
            years_experience=7,
            salary_expectation_aed=20000,
            current_role="PM",
            visa_status=None,
            notice_period=None,
        )

        resolution = _mock_identity_resolution(action="merge", matched_user_id="existing-user-789", confidence=1.0)

        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.rico_jotform_webhook.find_identity_candidates", return_value=[candidate]), \
             patch("src.rico_jotform_webhook.map_identity_flow", return_value=resolution), \
             patch("src.repositories.onboarding_repo.mark_onboarding_complete"):
            result = handle_jotform_submission(
                {"submissionID": "sub-telegram-1", "telegram_username": "@telegram_user", "consent": True}
            )

        assert result["status"] == "ok"
        db.upsert_user.assert_called_once()


# ── Conflict on strong match → pending_identity_confirmation ───────────────────

class TestConflictOnStrongMatch:
    def test_pending_confirmation_on_conflict(self):
        """When there's a conflict on strong match, should return pending_identity_confirmation."""
        from src.rico_jotform_webhook import handle_jotform_submission
        from src.services.profile_context_resolver import ProfileContext

        db = _mock_db()
        candidate = ProfileContext(
            user_id="existing-user-conflict",
            name="Conflict User",
            email="different@example.com",
            phone=None,
            telegram_username=None,
            target_roles=["Engineer"],
            preferred_cities=["Dubai"],
            skills=["Python"],
            industries=[],
            years_experience=5,
            salary_expectation_aed=15000,
            current_role="Developer",
            visa_status=None,
            notice_period=None,
        )

        resolution = _mock_identity_resolution(action="ask_user", matched_user_id="existing-user-conflict", confidence=0.6)

        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.rico_jotform_webhook.find_identity_candidates", return_value=[candidate]), \
             patch("src.rico_jotform_webhook.map_identity_flow", return_value=resolution):
            result = handle_jotform_submission(
                {"submissionID": "sub-conflict-1", "email": "new@example.com", "consent": True}
            )

        assert result["status"] == "accepted"
        assert result["reason"] == "pending_identity_confirmation"
        assert "identity_resolution" in result
        # Verify that upsert_user was NOT called (pending confirmation)
        db.upsert_user.assert_not_called()
        # Verify that webhook event was marked as pending
        db.mark_webhook_event_processed.assert_called_once()
        call_kwargs = db.mark_webhook_event_processed.call_args[1]
        assert call_kwargs["status"] == "pending_identity_confirmation"


# ── Weak/empty signal → existing missing-user or ignored behavior ──────────────

class TestWeakSignal:
    def test_weak_signal_ignored(self):
        """When signal is too weak, should return ignored with weak_identity_signal."""
        from src.rico_jotform_webhook import handle_jotform_submission

        db = _mock_db()
        resolution = _mock_identity_resolution(action="ignore", matched_user_id=None, confidence=0.0)

        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.rico_jotform_webhook.find_identity_candidates", return_value=[]), \
             patch("src.rico_jotform_webhook.map_identity_flow", return_value=resolution):
            result = handle_jotform_submission(
                {"submissionID": "sub-weak-1", "email": "weak@example.com", "consent": True}
            )

        assert result["status"] == "ignored"
        assert result["reason"] == "weak_identity_signal"
        assert "identity_resolution" in result
        db.upsert_user.assert_not_called()
        db.mark_webhook_event_processed.assert_called_once()
        call_kwargs = db.mark_webhook_event_processed.call_args[1]
        assert call_kwargs["status"] == "ignored_identity_signal"


# ── Duplicate submission → still returns duplicate before identity lookup ──────

class TestDuplicateSubmission:
    def test_duplicate_before_identity_lookup(self):
        """Duplicate submission_id should return duplicate before identity lookup is called."""
        from src.rico_jotform_webhook import handle_jotform_submission

        db = _mock_db()
        db.register_webhook_event.return_value = False  # Simulate duplicate

        env = {k: v for k, v in os.environ.items() if k != "JOTFORM_FORM_ID"}
        with patch("src.rico_jotform_webhook.RicoDB", return_value=db), \
             patch.dict(os.environ, env, clear=True), \
             patch("src.rico_jotform_webhook.find_identity_candidates") as mock_find, \
             patch("src.rico_jotform_webhook.map_identity_flow") as mock_map:
            result = handle_jotform_submission(
                {"submissionID": "sub-dup-2", "email": "user@example.com", "consent": True}
            )

        assert result["status"] == "ignored"
        assert result["reason"] == "duplicate"
        # Verify that identity lookup was NOT called (duplicate check comes first)
        mock_find.assert_not_called()
        mock_map.assert_not_called()


# ── Helper function tests ───────────────────────────────────────────────────────

class TestBuildIdentitySignal:
    def test_builds_signal_from_mapped_payload(self):
        from src.rico_jotform_webhook import _build_identity_signal

        mapped = {
            "user": {
                "external_user_id": "user@example.com",
                "name": "Test User",
                "email": "user@example.com",
                "phone": "+971501234567",
                "telegram_username": "@testuser",
            },
            "profile": {
                "target_roles": ["Engineer"],
                "skills": ["Python"],
            },
        }

        signal = _build_identity_signal(mapped)

        assert signal.source == "jotform"
        assert signal.user_id == "user@example.com"
        assert signal.email == "user@example.com"
        assert signal.phone == "+971501234567"
        assert signal.telegram_username == "@testuser"
        assert signal.name == "Test User"
        assert signal.profile is not None


class TestIdentityResolutionMetadata:
    def test_serializes_resolution_to_json_safe_dict(self):
        from src.rico_jotform_webhook import _identity_resolution_metadata
        from src.services.identity_flow_mapper import IdentityResolution

        resolution = IdentityResolution(
            action="merge",
            confidence=0.95,
            matched_user_id="user-123",
            reasons=["email match"],
            conflicts={"email": ("new@example.com", "old@example.com")},
            missing_fields=["skills"],
        )

        meta = _identity_resolution_metadata(resolution)

        assert meta["action"] == "merge"
        assert meta["confidence"] == 0.95
        assert meta["matched_user_id"] == "user-123"
        assert meta["reasons"] == ["email match"]
        assert meta["conflicts"]["email"] == ["new@example.com", "old@example.com"]
        assert meta["missing_fields"] == ["skills"]
