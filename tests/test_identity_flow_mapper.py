"""Tests for identity flow mapper.

Covers:
* Low-quality signals → ignore
* Strong matches (email, phone, telegram, user_id) → merge
* Conflicting strong matches → ask_user
* Medium matches (name + field overlap) → ask_user
* No match → create_new
* Missing fields and conflicts detection
"""

from __future__ import annotations

import pytest

from src.services.identity_flow_mapper import (
    IdentityResolution,
    IdentitySignal,
    map_identity_flow,
)
from src.services.profile_context_resolver import ProfileContext, resolve_profile_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile(
    user_id: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    telegram_username: str | None = None,
    **kwargs,
) -> ProfileContext:
    data = {
        "name": name,
        "email": email,
        "phone": phone,
        "telegram_username": telegram_username,
        **kwargs,
    }
    return resolve_profile_context(user_id, {k: v for k, v in data.items() if v is not None})


# ---------------------------------------------------------------------------
# Low-quality / empty signals
# ---------------------------------------------------------------------------

class TestLowQualitySignal:
    def test_completely_empty_signal(self):
        signal = IdentitySignal(source="chat")
        resolution = map_identity_flow(signal, [])
        assert resolution.action == "ignore"
        assert resolution.confidence == 0.0
        assert "lacks any identifiable field" in resolution.reasons[0]

    def test_signal_with_only_source(self):
        signal = IdentitySignal(source="jotform")
        resolution = map_identity_flow(signal, [])
        assert resolution.action == "ignore"

    def test_signal_with_empty_strings(self):
        signal = IdentitySignal(source="chat", email="", phone="", name="")
        resolution = map_identity_flow(signal, [])
        assert resolution.action == "ignore"


# ---------------------------------------------------------------------------
# Strong single matches → merge
# ---------------------------------------------------------------------------

class TestStrongMatchMerge:
    def test_email_exact_match(self):
        candidate = _profile("u1", name="Ali", email="ali@example.com", skills=["Python"])
        signal = IdentitySignal(source="jotform", email="ali@example.com", name="Ali")
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"
        assert resolution.matched_user_id == "u1"
        assert resolution.confidence >= 0.9
        assert "Strong match" in resolution.reasons[0]

    def test_phone_exact_match(self):
        candidate = _profile("u1", name="Ali", phone="+971501234567")
        signal = IdentitySignal(source="telegram", phone="+971 50 123 4567")
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"
        assert resolution.matched_user_id == "u1"

    def test_telegram_username_match(self):
        candidate = _profile("u1", telegram_username="ali_dubai")
        signal = IdentitySignal(source="telegram", telegram_username="@ali_dubai")
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"
        assert resolution.matched_user_id == "u1"

    def test_user_id_exact_match(self):
        candidate = _profile("u1", name="Ali", email="ali@example.com")
        signal = IdentitySignal(source="chat", user_id="u1", email="ali@example.com")
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"
        assert resolution.matched_user_id == "u1"

    def test_email_case_insensitive(self):
        candidate = _profile("u1", email="Ali@Example.com")
        signal = IdentitySignal(source="jotform", email="ali@example.com")
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"
        assert resolution.matched_user_id == "u1"

    def test_phone_normalization(self):
        candidate = _profile("u1", phone="971501234567")
        signal = IdentitySignal(source="jotform", phone="+971-50-123-4567")
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"


# ---------------------------------------------------------------------------
# Conflicts → ask_user
# ---------------------------------------------------------------------------

class TestConflictsAskUser:
    def test_conflicting_email(self):
        candidate = _profile("u1", email="ali@example.com", phone="+971501234567")
        signal = IdentitySignal(
            source="jotform",
            email="other@example.com",
            phone="+971501234567",
        )
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "ask_user"
        assert "email" in resolution.conflicts
        assert resolution.conflicts["email"] == ("other@example.com", "ali@example.com")

    def test_conflicting_phone(self):
        candidate = _profile("u1", email="ali@example.com", phone="+971501234567")
        signal = IdentitySignal(
            source="jotform",
            email="ali@example.com",
            phone="+971509876543",
        )
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "ask_user"
        assert "phone" in resolution.conflicts

    def test_conflicting_telegram(self):
        candidate = _profile("u1", telegram_username="ali_dubai", email="ali@example.com")
        signal = IdentitySignal(
            source="telegram",
            telegram_username="ali_abu_dhabi",
            email="ali@example.com",
        )
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "ask_user"
        assert "telegram_username" in resolution.conflicts


# ---------------------------------------------------------------------------
# Multiple strong matches → ask_user
# ---------------------------------------------------------------------------

class TestMultipleStrongMatches:
    def test_two_candidates_same_email(self):
        # This shouldn't happen in practice, but test the safety path
        c1 = _profile("u1", email="ali@example.com")
        c2 = _profile("u2", email="ali@example.com")
        signal = IdentitySignal(source="jotform", email="ali@example.com")
        resolution = map_identity_flow(signal, [c1, c2])
        assert resolution.action == "ask_user"
        assert resolution.confidence < 0.5
        assert "Multiple profiles match strongly" in resolution.reasons[0]

    def test_email_and_phone_match_different_candidates(self):
        c1 = _profile("u1", email="ali@example.com")
        c2 = _profile("u2", phone="+971501234567")
        signal = IdentitySignal(source="jotform", email="ali@example.com", phone="+971501234567")
        resolution = map_identity_flow(signal, [c1, c2])
        assert resolution.action == "ask_user"


# ---------------------------------------------------------------------------
# Medium matches → ask_user
# ---------------------------------------------------------------------------

class TestMediumMatchAskUser:
    def test_name_match_with_skill_overlap(self):
        candidate = _profile("u1", name="ali", skills=["Python", "SQL"], current_role="Developer")
        signal_profile = resolve_profile_context("incoming", {
            "name": "Ali",
            "skills": ["Python", "React"],
            "current_role": "Developer",
        })
        signal = IdentitySignal(source="chat", name="Ali", profile=signal_profile)
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "ask_user"
        assert resolution.matched_user_id == "u1"
        assert "Medium match" in resolution.reasons[0]

    def test_name_match_no_overlap(self):
        candidate = _profile("u1", name="ali", skills=["Python"])
        signal_profile = resolve_profile_context("incoming", {
            "name": "Ali",
            "skills": ["Marketing"],
        })
        signal = IdentitySignal(source="chat", name="Ali", profile=signal_profile)
        resolution = map_identity_flow(signal, [candidate])
        # Name match only, no field overlap → weak → create_new
        assert resolution.action == "create_new"


# ---------------------------------------------------------------------------
# No match → create_new
# ---------------------------------------------------------------------------

class TestNoMatchCreateNew:
    def test_no_candidates(self):
        signal = IdentitySignal(source="jotform", email="new@example.com", name="New User")
        resolution = map_identity_flow(signal, [])
        assert resolution.action == "create_new"
        assert resolution.confidence == 0.0

    def test_no_overlap_with_candidates(self):
        c1 = _profile("u1", email="ali@example.com", name="Ali")
        signal = IdentitySignal(source="jotform", email="bob@example.com", name="Bob")
        resolution = map_identity_flow(signal, [c1])
        assert resolution.action == "create_new"

    def test_weak_field_overlap_only(self):
        c1 = _profile("u1", skills=["Python"])
        signal_profile = resolve_profile_context("incoming", {"skills": ["Python"]})
        signal = IdentitySignal(source="chat", email="new@example.com", profile=signal_profile)
        resolution = map_identity_flow(signal, [c1])
        # One skill overlap without name → weak, but email is new → create_new
        assert resolution.action == "create_new"


# ---------------------------------------------------------------------------
# Missing fields
# ---------------------------------------------------------------------------

class TestMissingFields:
    def test_merge_reports_missing_fields(self):
        candidate = _profile("u1", email="ali@example.com", skills=["Python"])
        signal_profile = resolve_profile_context("incoming", {
            "email": "ali@example.com",
            "years_experience": 5,
            "preferred_cities": ["Dubai"],
        })
        signal = IdentitySignal(source="jotform", email="ali@example.com", profile=signal_profile)
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"
        assert "years_experience" in resolution.missing_fields
        assert "preferred_cities" in resolution.missing_fields
        assert "skills" not in resolution.missing_fields  # candidate already has it

    def test_no_missing_fields_when_fully_overlapping(self):
        candidate = _profile("u1", email="ali@example.com", skills=["Python"], years_experience=5)
        signal_profile = resolve_profile_context("incoming", {
            "email": "ali@example.com",
            "skills": ["Python"],
            "years_experience": 5,
        })
        signal = IdentitySignal(source="jotform", email="ali@example.com", profile=signal_profile)
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.missing_fields == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_phone_normalization_different_formats(self):
        candidate = _profile("u1", phone="971501234567")
        signal = IdentitySignal(source="jotform", phone="+971-50-123-4567")
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"

    def test_telegram_at_sign_normalized(self):
        candidate = _profile("u1", telegram_username="ali")
        signal = IdentitySignal(source="telegram", telegram_username="@Ali")
        resolution = map_identity_flow(signal, [candidate])
        assert resolution.action == "merge"

    def test_multiple_candidates_none_match(self):
        c1 = _profile("u1", email="a@example.com")
        c2 = _profile("u2", email="b@example.com")
        signal = IdentitySignal(source="jotform", email="c@example.com")
        resolution = map_identity_flow(signal, [c1, c2])
        assert resolution.action == "create_new"
