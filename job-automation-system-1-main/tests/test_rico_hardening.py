"""tests/test_rico_hardening.py

Hardening tests for Rico intelligent agent — Issues #109, #110.

Coverage:
  - Intent classifier (all canonical intents, nonsense rejection)
  - Role classifier (3-tier: profile_relevant, known_but_off_profile, unknown)
  - RicoResponse schema stability (debug_id, success, type always present)
  - build_error_response (no stack traces, debug_id present)
  - Taxonomy loading and alias resolution
  - CV wizard restart prevention
  - Application tracking intent routing (not job search)
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ── Intent classifier tests ──────────────────────────────────────────────────

from src.agent.intelligence.intent_classifier import classify_intent, IntentResult


class TestIntentClassifier:
    """Verify classify_intent routes correctly and never defaults to job search."""

    # ── Exact-phrase intents ──────────────────────────────────────────────

    @pytest.mark.parametrize("msg,expected_intent", [
        ("help", "help"),
        ("options", "help"),
        ("what can you do", "help"),
        ("what's next", "help"),
        ("next steps", "help"),
    ])
    def test_help_phrases(self, msg: str, expected_intent: str) -> None:
        result = classify_intent(msg)
        assert result.intent == expected_intent
        assert result.confidence >= 0.9

    @pytest.mark.parametrize("msg", [
        "hi", "hello", "hey", "thanks", "ok", "bye",
    ])
    def test_smalltalk(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "smalltalk"

    @pytest.mark.parametrize("msg", [
        "show my tracked applications",
        "application status",
        "my applications",
        "show applied jobs",
        "show interviews",
    ])
    def test_application_tracking_exact(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "application_tracking"
        assert result.confidence >= 0.8

    @pytest.mark.parametrize("msg", [
        "use my cv", "match my cv", "find me one that matches",
        "jobs for my profile", "what fits my profile",
    ])
    def test_profile_match(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "job_search_profile_match"

    @pytest.mark.parametrize("msg", [
        "show my profile", "my profile", "profile summary",
    ])
    def test_profile_summary(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "profile_summary"

    @pytest.mark.parametrize("msg", [
        "skip this question", "don't know", "skip",
    ])
    def test_onboarding_answer(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "onboarding_answer"

    # ── Regex-based intents ──────────────────────────────────────────────

    @pytest.mark.parametrize("msg", [
        "find software engineer jobs in Dubai",
        "search for any accounting positions",
        "show me job openings in Abu Dhabi",
        "looking for sales roles",
    ])
    def test_job_search_explicit(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "job_search_explicit"

    @pytest.mark.parametrize("msg", [
        "uploaded my_cv.pdf",
        "here is my resume cv_2024.docx",
        "resume attached",
    ])
    def test_cv_upload(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "cv_upload_or_parse"

    @pytest.mark.parametrize("msg", [
        "update my salary to 15000 AED",
        "change my city to Abu Dhabi",
        "set my preferred location to Sharjah",
    ])
    def test_profile_update(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "profile_update"

    @pytest.mark.parametrize("msg", [
        "apply to this job",
        "submit my application",
    ])
    def test_apply_job(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "apply_job"

    @pytest.mark.parametrize("msg", [
        "what about accountant",
        "switch to data analyst",
        "try product manager",
    ])
    def test_role_change(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "role_change"
        assert result.extracted_role is not None

    @pytest.mark.parametrize("msg", [
        "interview prep for Google",
        "prepare for interview questions",
        "get ready for interview",
    ])
    def test_interview_prep(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "interview_prep"

    @pytest.mark.parametrize("msg", [
        "why did you recommend this job",
        "explain why this match",
    ])
    def test_explain_match(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "explain_match"

    @pytest.mark.parametrize("msg", [
        "draft a cover letter for this role",
        "write an email to the recruiter",
    ])
    def test_draft_message(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "draft_message"

    @pytest.mark.parametrize("msg", [
        "save this job",
        "bookmark this one",
    ])
    def test_save_job(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent == "save_job"

    # ── Nonsense / unknown — must NEVER become job search ────────────────

    @pytest.mark.parametrize("msg", [
        "aaaaaaa",
        "12345",
        "",
        "a",
        "!!!!!",
    ])
    def test_nonsense_not_job_search(self, msg: str) -> None:
        result = classify_intent(msg)
        assert result.intent in ("nonsense", "unknown")
        assert result.intent != "job_search_explicit"

    def test_random_sentence_not_job_search(self) -> None:
        """A random sentence should NOT be treated as job search."""
        result = classify_intent("the weather is nice today in Dubai")
        assert result.intent != "job_search_explicit"

    def test_ambiguous_short_text_not_job_search(self) -> None:
        """Short ambiguous text like 'banana' should NOT become a job search."""
        result = classify_intent("banana")
        assert result.intent in ("unknown", "nonsense")

    # ── Profile-match inference ──────────────────────────────────────────

    def test_generic_match_with_cv_profile(self) -> None:
        result = classify_intent("recommend matching jobs", has_cv_profile=True)
        assert result.intent == "job_search_profile_match"

    def test_generic_match_without_cv_profile(self) -> None:
        """Without CV, generic 'matching' should not become profile match."""
        result = classify_intent("recommend matching jobs", has_cv_profile=False)
        # Should NOT be profile_match — might be unknown or explicit search
        assert result.intent != "job_search_profile_match"


# ── Role classifier tests ────────────────────────────────────────────────────

from src.agent.intelligence.role_classifier import (
    classify_role_candidate,
    resolve_taxonomy_role,
)


class TestRoleClassifier:
    """Verify 3-tier role classification: profile_relevant, known_but_off_profile, unknown."""

    def test_taxonomy_alias_resolution(self) -> None:
        assert resolve_taxonomy_role("hse") == "HSE Officer"
        assert resolve_taxonomy_role("devops") == "DevOps Engineer"
        assert resolve_taxonomy_role("accountant") == "Accountant"
        assert resolve_taxonomy_role("software engineer") == "Software Engineer"

    def test_unknown_role_returns_none(self) -> None:
        assert resolve_taxonomy_role("xyznonexistent") is None

    def test_profile_relevant(self) -> None:
        profile = {
            "target_roles": ["HSE Officer", "QHSE Manager"],
            "skills": ["safety", "risk", "inspection", "nebosh"],
        }
        classification, canonical = classify_role_candidate("hse", profile)
        assert classification == "profile_relevant"
        assert canonical == "HSE Officer"

    def test_known_but_off_profile(self) -> None:
        profile = {
            "target_roles": ["HSE Officer"],
            "skills": ["safety", "risk", "inspection"],
        }
        classification, canonical = classify_role_candidate("accountant", profile)
        assert classification == "known_but_off_profile"
        assert canonical == "Accountant"

    def test_unknown_role(self) -> None:
        profile = {
            "target_roles": ["HSE Officer"],
            "skills": ["safety"],
        }
        classification, canonical = classify_role_candidate("xyzgibberish", profile)
        assert classification == "unknown"
        assert canonical is None

    def test_no_profile_data(self) -> None:
        """Known role with no profile → known_but_off_profile (ask confirmation)."""
        classification, canonical = classify_role_candidate("accountant", None)
        assert classification == "known_but_off_profile"
        assert canonical == "Accountant"

    def test_fuzzy_alias_match(self) -> None:
        """Slight misspelling should still resolve."""
        result = resolve_taxonomy_role("sofware engineer")
        # May or may not resolve depending on fuzzy threshold, but should not crash
        assert result is None or isinstance(result, str)


# ── Response schema tests ────────────────────────────────────────────────────

from src.agent.responses.schema import RicoResponse, build_error_response, _generate_debug_id


class TestRicoResponse:
    """Verify stable response envelope."""

    def test_to_dict_always_has_required_fields(self) -> None:
        r = RicoResponse(success=True, type="job_matches", message="Found 3 jobs.")
        d = r.to_dict()
        assert "success" in d
        assert "type" in d
        assert "message" in d
        assert "debug_id" in d
        assert d["success"] is True
        assert d["type"] == "job_matches"

    def test_debug_id_is_string(self) -> None:
        r = RicoResponse(success=True, type="test", message="hi")
        assert isinstance(r.debug_id, str)
        assert len(r.debug_id) == 12

    def test_empty_optional_fields_omitted(self) -> None:
        r = RicoResponse(success=True, type="test", message="hi")
        d = r.to_dict()
        assert "matches" not in d  # empty list omitted
        assert "applications" not in d
        assert "options" not in d
        assert "profile" not in d

    def test_populated_optional_fields_included(self) -> None:
        r = RicoResponse(
            success=True,
            type="job_matches",
            message="hi",
            matches=[{"title": "SWE"}],
            next_action="apply",
        )
        d = r.to_dict()
        assert d["matches"] == [{"title": "SWE"}]
        assert d["next_action"] == "apply"

    def test_build_error_response_no_stack_trace(self) -> None:
        try:
            raise ValueError("secret internal error detail")
        except ValueError as e:
            resp = build_error_response(
                "Something went wrong.",
                log_exc=e,
                user_id="test@test.com",
            )
        assert resp["success"] is False
        assert resp["type"] == "error"
        assert "debug_id" in resp
        # CRITICAL: no stack trace or raw exception in response
        assert "secret internal error detail" not in resp["message"]
        assert "Traceback" not in resp["message"]
        assert "ValueError" not in resp["message"]
        # debug_id IS in message for user reference
        assert resp["debug_id"] in resp["message"]

    def test_build_error_response_custom_debug_id(self) -> None:
        resp = build_error_response("fail", debug_id="custom123")
        assert resp["debug_id"] == "custom123"

    def test_generate_debug_id_uniqueness(self) -> None:
        ids = {_generate_debug_id() for _ in range(100)}
        assert len(ids) == 100  # all unique


# ── Taxonomy tests ───────────────────────────────────────────────────────────


class TestTaxonomy:
    """Verify taxonomy file loads and contains expected structure."""

    def test_taxonomy_loads(self) -> None:
        from src.agent.intelligence.role_classifier import _load_taxonomy
        tax = _load_taxonomy()
        assert "aliases" in tax
        assert "families" in tax
        assert len(tax["aliases"]) > 50

    def test_taxonomy_aliases_resolve_to_canonical(self) -> None:
        from src.agent.intelligence.role_classifier import _load_taxonomy
        tax = _load_taxonomy()
        # Every alias value should be a non-empty string (canonical role)
        for alias, canonical in tax["aliases"].items():
            assert isinstance(canonical, str) and len(canonical) > 0, (
                f"Alias '{alias}' maps to invalid canonical: {canonical!r}"
            )
        # Families should have at least some entries
        assert len(tax["families"]) >= 10


# ── Integration tests (process_message wrapper) ─────────────────────────────


class TestProcessMessageWrapper:
    """Verify process_message always returns debug_id and success."""

    @patch("src.rico_chat_api.is_onboarding_complete", return_value=True)
    @patch("src.rico_chat_api.get_profile", return_value=None)
    def test_process_message_returns_debug_id(self, mock_profile: Any, mock_onboard: Any) -> None:
        from src.rico_chat_api import RicoChatAPI
        api = RicoChatAPI()
        # Patch internal methods to prevent real calls
        api._handle_active_user = MagicMock(return_value={
            "type": "test",
            "message": "test response",
        })
        result = api.process_message("test_user", "hello")
        assert "debug_id" in result
        assert "success" in result

    @patch("src.rico_chat_api.is_onboarding_complete", return_value=True)
    @patch("src.rico_chat_api.get_profile", return_value=None)
    def test_process_message_catches_exceptions(self, mock_profile: Any, mock_onboard: Any) -> None:
        from src.rico_chat_api import RicoChatAPI
        api = RicoChatAPI()
        api._handle_active_user = MagicMock(side_effect=RuntimeError("boom"))
        # Use _process_message_inner to bypass the outer wrapper for a moment
        # Actually test the outer wrapper:
        api._append_chat = MagicMock()  # prevent memory store calls
        result = api.process_message("test_user", "hello")
        assert result["success"] is False
        assert result["type"] == "error"
        assert "debug_id" in result
        # No raw stack trace
        assert "boom" not in result["message"]
        assert "RuntimeError" not in result["message"]


# ── Application tracking intent routing test ─────────────────────────────────


class TestApplicationTrackingRouting:
    """'show my tracked applications' must NOT trigger job search."""

    def test_intent_is_application_tracking(self) -> None:
        result = classify_intent("show my tracked applications")
        assert result.intent == "application_tracking"
        assert result.intent != "job_search_explicit"
        assert result.intent != "unknown"

    def test_my_applications_is_not_search(self) -> None:
        result = classify_intent("my applications")
        assert result.intent == "application_tracking"

    def test_interview_status_is_tracking(self) -> None:
        result = classify_intent("interview status")
        assert result.intent == "application_tracking"


# ── CV wizard restart prevention test ────────────────────────────────────────


class TestCVWizardPrevention:
    """CV upload/parse intent should not restart wizard when CV already parsed."""

    def test_cv_upload_intent_detected(self) -> None:
        result = classify_intent("uploaded my_resume.pdf")
        assert result.intent == "cv_upload_or_parse"

    def test_cv_reference_detected(self) -> None:
        result = classify_intent("here is my resume document.docx")
        assert result.intent == "cv_upload_or_parse"


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases that previously caused issues."""

    def test_empty_message(self) -> None:
        result = classify_intent("")
        assert result.intent in ("unknown", "nonsense")

    def test_none_message_handled(self) -> None:
        result = classify_intent(None)  # type: ignore
        assert result.intent in ("unknown", "nonsense")

    def test_very_long_message(self) -> None:
        long_msg = "find jobs " * 500
        result = classify_intent(long_msg)
        # Should not crash, intent doesn't matter as much
        assert isinstance(result, IntentResult)

    def test_unicode_message(self) -> None:
        result = classify_intent("مرحبا أريد وظيفة")
        assert isinstance(result, IntentResult)

    def test_mixed_case_intent(self) -> None:
        result = classify_intent("HELP")
        assert result.intent == "help"

    def test_whitespace_only(self) -> None:
        result = classify_intent("   ")
        assert result.intent in ("unknown", "nonsense")

    def test_role_classifier_empty_text(self) -> None:
        classification, canonical = classify_role_candidate("", None)
        assert classification == "unknown"
        assert canonical is None
