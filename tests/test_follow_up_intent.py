"""Regression tests for follow-up intent handling (issue #133)."""

import pytest

from src.agent.intelligence.intent_classifier import classify_intent, IntentResult


class TestFollowUpIntentRegression:
    """Test that follow-up phrases are not classified as job roles."""

    def test_both_please_is_follow_up_confirmation(self):
        """'both please' should be classified as follow_up_confirmation, not job role."""
        result = classify_intent("both please")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_both_is_follow_up_confirmation(self):
        """'both' should be classified as follow_up_confirmation."""
        result = classify_intent("both")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_keep_all_is_follow_up_confirmation(self):
        """'keep all' should be classified as follow_up_confirmation."""
        result = classify_intent("keep all")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_keep_them_all_is_follow_up_confirmation(self):
        """'keep them all' should be classified as follow_up_confirmation."""
        result = classify_intent("keep them all")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_yes_keep_all_is_follow_up_confirmation(self):
        """'yes keep all' should be classified as follow_up_confirmation."""
        result = classify_intent("yes keep all")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_continue_is_follow_up_confirmation(self):
        """'continue' should be classified as follow_up_confirmation."""
        result = classify_intent("continue")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_ok_continue_is_follow_up_confirmation(self):
        """'ok continue' should be classified as follow_up_confirmation."""
        result = classify_intent("ok continue")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_yes_is_follow_up_confirmation(self):
        """'yes' should be classified as follow_up_confirmation."""
        result = classify_intent("yes")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_confirm_is_follow_up_confirmation(self):
        """'confirm' should be classified as follow_up_confirmation."""
        result = classify_intent("confirm")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_proceed_is_follow_up_confirmation(self):
        """'proceed' should be classified as follow_up_confirmation."""
        result = classify_intent("proceed")
        assert result.intent == "follow_up_confirmation"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_follow_up_phrases_not_job_search_explicit(self):
        """Follow-up phrases should not be classified as job_search_explicit."""
        for phrase in ["both please", "keep all", "continue", "yes", "no"]:
            result = classify_intent(phrase)
            assert result.intent != "job_search_explicit", f"{phrase} should not be job_search_explicit"

    def test_follow_up_phrases_not_role_change(self):
        """Follow-up phrases should not be classified as role_change."""
        for phrase in ["both please", "keep all", "continue", "yes", "no"]:
            result = classify_intent(phrase)
            assert result.intent != "role_change", f"{phrase} should not be role_change"

    def test_follow_up_phrases_not_unknown(self):
        """Follow-up phrases should not be classified as unknown."""
        for phrase in ["both please", "keep all", "continue", "yes", "no"]:
            result = classify_intent(phrase)
            assert result.intent != "unknown", f"{phrase} should not be unknown"

    def test_case_insensitive_follow_up(self):
        """Follow-up phrases should be case-insensitive."""
        result = classify_intent("BOTH PLEASE")
        assert result.intent == "follow_up_confirmation"

        result = classify_intent("Keep All")
        assert result.intent == "follow_up_confirmation"

        result = classify_intent("CONTINUE")
        assert result.intent == "follow_up_confirmation"
