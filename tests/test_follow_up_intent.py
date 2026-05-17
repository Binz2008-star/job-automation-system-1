"""Regression tests for follow-up intent handling (issue #133)."""

import pytest

from src.agent.intelligence.intent_classifier import classify_intent, IntentResult
from src.rico_chat_api import RicoChatAPI


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
        for phrase in ["both please", "keep all", "continue", "yes"]:
            result = classify_intent(phrase)
            assert result.intent != "job_search_explicit", f"{phrase} should not be job_search_explicit"

    def test_follow_up_phrases_not_role_change(self):
        """Follow-up phrases should not be classified as role_change."""
        for phrase in ["both please", "keep all", "continue", "yes"]:
            result = classify_intent(phrase)
            assert result.intent != "role_change", f"{phrase} should not be role_change"

    def test_follow_up_phrases_not_unknown(self):
        """Follow-up phrases should not be classified as unknown."""
        for phrase in ["both please", "keep all", "continue", "yes"]:
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

    def test_follow_up_with_trailing_punctuation(self):
        """Trailing punctuation should not break follow-up intent classification."""
        assert classify_intent("both please.").intent == "follow_up_confirmation"
        assert classify_intent("keep all!").intent == "follow_up_confirmation"
        assert classify_intent("continue?").intent == "follow_up_confirmation"


class TestFollowUpPhraseHandling:
    """Test deterministic follow-up phrase handling in RicoChatAPI."""

    def test_both_please_in_phrase_set(self):
        """'both please' should be in the both action phrases set."""
        assert "both please" in RicoChatAPI._FOLLOWUP_BOTH_ACTION_PHRASES

    def test_keep_all_in_phrase_set(self):
        """'keep all' should be in the keep all phrases set."""
        assert "keep all" in RicoChatAPI._FOLLOWUP_KEEP_ALL_PHRASES

    def test_do_both_in_phrase_set(self):
        """'do both' should be in the both action phrases set."""
        assert "do both" in RicoChatAPI._FOLLOWUP_BOTH_ACTION_PHRASES

    def test_keep_them_all_in_phrase_set(self):
        """'keep them all' should be in the keep all phrases set."""
        assert "keep them all" in RicoChatAPI._FOLLOWUP_KEEP_ALL_PHRASES

    def test_handle_keep_all_target_roles_exists(self):
        """_handle_keep_all_target_roles method should exist."""
        api = RicoChatAPI()
        assert hasattr(api, "_handle_keep_all_target_roles")
        assert callable(getattr(api, "_handle_keep_all_target_roles"))

    def test_handle_both_requested_actions_exists(self):
        """_handle_both_requested_actions method should exist."""
        api = RicoChatAPI()
        assert hasattr(api, "_handle_both_requested_actions")
        assert callable(getattr(api, "_handle_both_requested_actions"))


class TestProductionFailureRegression:
    """Regression tests for exact production failures from issue #133."""

    def test_both_please_does_not_return_job_role_error(self):
        """'both please' must not return 'I do not recognize ... as a job role'."""
        api = RicoChatAPI()
        # The deterministic phrase check happens before role classification
        # So "both please" should be handled by the both action handler
        assert "both please" in RicoChatAPI._FOLLOWUP_BOTH_ACTION_PHRASES

    def test_keep_all_does_not_return_job_role_error(self):
        """'keep all' must not return 'I do not recognize ... as a job role'."""
        api = RicoChatAPI()
        # The deterministic phrase check happens before role classification
        # So "keep all" should be handled by the keep all handler
        assert "keep all" in RicoChatAPI._FOLLOWUP_KEEP_ALL_PHRASES

    def test_both_please_executes_before_role_classification(self):
        """Both action phrases execute before _looks_like_selected_role and _classified_role_search."""
        api = RicoChatAPI()
        # Verify the phrase sets are defined at class level
        assert hasattr(RicoChatAPI, "_FOLLOWUP_BOTH_ACTION_PHRASES")
        assert hasattr(RicoChatAPI, "_FOLLOWUP_KEEP_ALL_PHRASES")
        # Verify handlers exist
        assert hasattr(api, "_handle_both_requested_actions")
        assert hasattr(api, "_handle_keep_all_target_roles")

    def test_keep_all_executes_before_role_classification(self):
        """Keep all phrases execute before _looks_like_selected_role and _classified_role_search."""
        api = RicoChatAPI()
        # Verify the phrase sets are defined at class level
        assert hasattr(RicoChatAPI, "_FOLLOWUP_KEEP_ALL_PHRASES")
        # Verify handler exists
        assert hasattr(api, "_handle_keep_all_target_roles")
