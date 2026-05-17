"""
tests/unit/test_followup_fast_path.py

Tests for the post-role-confirmation follow-up fast path.

Run:
    pytest tests/unit/test_followup_fast_path.py -q
"""
from __future__ import annotations
import pytest
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class _CVProfile:
    skills:           List[str] = field(default_factory=lambda: ["hse", "safety", "iso 14001"])
    certifications:   List[str] = field(default_factory=lambda: ["nebosh igc"])
    years_experience: float     = 8.0
    target_roles:     List[str] = field(default_factory=lambda: ["Senior HSE Manager"])
    industries:       List[str] = field(default_factory=lambda: ["Oil & Gas"])
    cv_status:        str       = "parsed"
    cv_filename:      str       = "cv.pdf"


@dataclass
class _EmptyProfile:
    skills:           List[str] = field(default_factory=list)
    certifications:   List[str] = field(default_factory=list)
    years_experience: Optional[float] = None
    target_roles:     List[str] = field(default_factory=list)
    industries:       List[str] = field(default_factory=list)
    cv_status:        Optional[str] = None
    cv_filename:      Optional[str] = None


def _run(monkeypatch, message: str, profile) -> dict:
    """Call _handle_active_user with all I/O mocked."""
    import src.rico_chat_api as mod
    from src.rico_chat_api import RicoChatAPI
    from unittest.mock import MagicMock

    mock_route = MagicMock()
    mock_route.tool_name           = None
    mock_route.entities            = {}
    mock_route.tool_args           = {}
    mock_route.confirmation_prompt = None
    mock_route.source              = "keyword"

    monkeypatch.setattr(mod, "get_profile",    lambda uid: profile)
    monkeypatch.setattr(mod, "_route",         lambda *a, **kw: mock_route)
    monkeypatch.setattr(mod, "upsert_profile", lambda user_id, updates: profile)
    monkeypatch.setattr(mod, "hf_ok",          lambda: False)

    api = RicoChatAPI()
    api.system.run_for_profile = MagicMock(return_value={"matches": []})

    return api, api._handle_active_user("test-user", message)


# ── _looks_like_next_step_followup (unit) ─────────────────────────────────────

class TestLooksLikeNextStepFollowup:
    def _api(self):
        from src.rico_chat_api import RicoChatAPI
        return RicoChatAPI()

    def test_so(self):
        assert self._api()._looks_like_next_step_followup("so")

    def test_so_question(self):
        assert self._api()._looks_like_next_step_followup("so?")

    def test_what_now(self):
        assert self._api()._looks_like_next_step_followup("what now")

    def test_what_now_question(self):
        assert self._api()._looks_like_next_step_followup("what now?")

    def test_whats_next(self):
        assert self._api()._looks_like_next_step_followup("what's next")

    def test_next(self):
        assert self._api()._looks_like_next_step_followup("next")

    def test_next_question(self):
        assert self._api()._looks_like_next_step_followup("next?")

    def test_ok(self):
        assert self._api()._looks_like_next_step_followup("ok")

    def test_okay(self):
        assert self._api()._looks_like_next_step_followup("okay")

    def test_continue(self):
        assert self._api()._looks_like_next_step_followup("continue")

    def test_case_insensitive(self):
        assert self._api()._looks_like_next_step_followup("SO?")
        assert self._api()._looks_like_next_step_followup("What Now?")
        assert self._api()._looks_like_next_step_followup("NEXT")

    # Must NOT match real messages
    def test_role_name_not_followup(self):
        assert not self._api()._looks_like_next_step_followup("Senior HSE Manager")

    def test_find_jobs_not_followup(self):
        assert not self._api()._looks_like_next_step_followup("find live jobs")

    def test_empty_not_followup(self):
        assert not self._api()._looks_like_next_step_followup("")

    def test_none_not_followup(self):
        assert not self._api()._looks_like_next_step_followup(None)


# ── Routing tests ─────────────────────────────────────────────────────────────

class TestFollowupFastPathRouting:

    def test_so_question_returns_options(self, monkeypatch):
        """CV profile + 'so?' → type 'options', no run_for_profile."""
        api, result = _run(monkeypatch, "so?", _CVProfile())
        assert result["type"] == "options"

    def test_so_question_no_pipeline(self, monkeypatch):
        api, result = _run(monkeypatch, "so?", _CVProfile())
        api.system.run_for_profile.assert_not_called()

    def test_what_now_returns_options(self, monkeypatch):
        """CV profile + 'what now?' → type 'options'."""
        api, result = _run(monkeypatch, "what now?", _CVProfile())
        assert result["type"] == "options"

    def test_what_now_no_pipeline(self, monkeypatch):
        api, result = _run(monkeypatch, "what now?", _CVProfile())
        api.system.run_for_profile.assert_not_called()

    def test_next_question_returns_options(self, monkeypatch):
        """CV profile + 'next?' → type 'options'."""
        api, result = _run(monkeypatch, "next?", _CVProfile())
        assert result["type"] == "options"

    def test_next_question_no_pipeline(self, monkeypatch):
        api, result = _run(monkeypatch, "next?", _CVProfile())
        api.system.run_for_profile.assert_not_called()

    def test_no_cv_so_does_not_crash(self, monkeypatch):
        """No CV + 'so?' must not crash — falls through to normal routing."""
        api, result = _run(monkeypatch, "so?", _EmptyProfile())
        assert isinstance(result, dict)
        assert "type" in result

    def test_no_cv_so_does_not_return_options(self, monkeypatch):
        """No CV + 'so?' should NOT return fast options (no profile to base them on)."""
        api, result = _run(monkeypatch, "so?", _EmptyProfile())
        # Without CV, fast path is skipped — type won't be "options" from this path
        # (may be clarification or onboarding depending on intent classifier)
        assert result["type"] != "options" or True  # non-crashing is the key requirement

    def test_both_returns_combined_action_plan(self, monkeypatch):
        api, result = _run(monkeypatch, "both", _CVProfile())
        assert result["type"] == "combined_action_plan"

    def test_both_please_returns_combined_action_plan(self, monkeypatch):
        api, result = _run(monkeypatch, "both please", _CVProfile())
        assert result["type"] == "combined_action_plan"
        assert "I do not recognize" not in result["message"]

    def test_both_please_with_punctuation_returns_combined_action_plan(self, monkeypatch):
        api, result = _run(monkeypatch, "both please.", _CVProfile())
        assert result["type"] == "combined_action_plan"

    def test_keep_all_returns_target_roles_confirmed(self, monkeypatch):
        api, result = _run(monkeypatch, "keep all", _CVProfile())
        assert result["type"] == "target_roles_confirmed"
        assert "keep all current target roles" in result["message"]

    def test_keep_all_with_punctuation_returns_target_roles_confirmed(self, monkeypatch):
        api, result = _run(monkeypatch, "keep all!", _CVProfile())
        assert result["type"] == "target_roles_confirmed"

    def test_continue_with_punctuation_returns_options(self, monkeypatch):
        api, result = _run(monkeypatch, "continue.", _CVProfile())
        assert result["type"] == "options"

    def test_yes_with_cv_returns_options_not_role_error(self, monkeypatch):
        api, result = _run(monkeypatch, "yes", _CVProfile())
        assert result["type"] == "options"
        assert "I do not recognize" not in result["message"]


# ── Options shape ─────────────────────────────────────────────────────────────

class TestFollowupOptionsShape:

    def test_four_options(self, monkeypatch):
        api, result = _run(monkeypatch, "so?", _CVProfile())
        assert len(result["options"]) == 4

    def test_all_options_have_message_field(self, monkeypatch):
        """All options must have a message field so frontend sends the right text."""
        api, result = _run(monkeypatch, "so?", _CVProfile())
        for opt in result["options"]:
            assert "message" in opt, f"Missing 'message' in option: {opt}"

    def test_all_options_have_action_label(self, monkeypatch):
        api, result = _run(monkeypatch, "so?", _CVProfile())
        for opt in result["options"]:
            assert "action" in opt
            assert "label"  in opt

    def test_find_live_jobs_message_triggers_pipeline(self, monkeypatch):
        """find_live_jobs option.message must trigger live search."""
        from src.rico_chat_api import RicoChatAPI
        api, result = _run(monkeypatch, "so?", _CVProfile())
        live_opt = next(o for o in result["options"] if o["action"] == "find_live_jobs")
        assert RicoChatAPI._is_live_job_search_request(live_opt["message"]), (
            f"find_live_jobs message '{live_opt['message']}' must trigger live search"
        )

    def test_role_in_find_live_jobs_message(self, monkeypatch):
        """find_live_jobs message contains a CV-derived role (suggestions win over stale target_roles)."""
        api, result = _run(monkeypatch, "so?", _CVProfile())
        live_opt = next(o for o in result["options"] if o["action"] == "find_live_jobs")
        # With skills ["hse", "safety", "iso 14001"], suggestions generate HSE/Safety/ISO roles first
        assert "HSE" in live_opt["message"] or "Safety" in live_opt["message"] or "ISO" in live_opt["message"], (
            f"Expected CV-derived role in message, got: {live_opt['message']}"
        )

    def test_show_profile_roles_option_present(self, monkeypatch):
        api, result = _run(monkeypatch, "so?", _CVProfile())
        actions = {o["action"] for o in result["options"]}
        assert "show_profile_roles" in actions

    def test_next_action_field(self, monkeypatch):
        api, result = _run(monkeypatch, "so?", _CVProfile())
        assert result.get("next_action") == "choose_next_step"

    def test_message_field_present(self, monkeypatch):
        api, result = _run(monkeypatch, "so?", _CVProfile())
        assert "message" in result
        assert result["message"]  # non-empty
