"""
tests/unit/test_role_confirmation.py

Required tests A–K from the spec.
Uses real RicoChatAPI with mocked external dependencies.

Run:
    pytest tests/unit/test_role_confirmation.py -q
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call


# ── Setup helpers ─────────────────────────────────────────────────────────────

def _make_api():
    """Build RicoChatAPI with all I/O mocked out."""
    patches = [
        patch("src.rico_memory.RicoMemoryStore"),
        patch("src.rico_agent.RicoAgent"),
        patch("src.rico_repo_adapter.RicoSystem"),
        patch("src.rico_openai_agent.RicoOpenAIAgent"),
    ]
    for p in patches:
        p.start()

    from src.rico_chat_api import RicoChatAPI
    api = RicoChatAPI()
    api.memory = MagicMock()
    api.memory.append_chat_message = MagicMock()
    api.system = MagicMock()
    api.system.run_for_profile = MagicMock(return_value={"matches": []})
    api.openai_agent = MagicMock()
    api.openai_agent.model = "gpt-4o"
    api.openai_agent.openai_available   = True
    api.openai_agent.deepseek_available = False
    api.openai_agent.hf_available       = False
    api.openai_agent.provider_available = True
    api.openai_agent.provider_state     = None

    for p in patches:
        p.stop()

    return api


def _cv_profile(**kwargs) -> dict:
    """Minimal CV profile dict."""
    base = {
        "cv_status":        "processed",
        "cv_filename":      "test_cv.pdf",
        "skills":           ["HSE Management", "ISO 14001", "Safety", "Compliance"],
        "certifications":   ["NEBOSH IGC", "ISO 14001 Lead Auditor"],
        "years_experience": 8,
        "industries":       ["Oil & Gas"],
        "target_roles":     ["Senior HSE Manager"],
    }
    base.update(kwargs)
    return base


def _empty_profile() -> dict:
    """Empty profile with no CV data."""
    return {
        "cv_status": None,
        "skills": [],
        "certifications": [],
        "years_experience": None,
        "industries": [],
        "target_roles": [],
    }

def _run_with_profile(api, message: str, profile: dict, route_entities=None) -> dict:
    """Call _handle_active_user with get_profile mocked to return profile."""
    from unittest.mock import MagicMock
    route_mock = MagicMock(
        tool_name=None, entities=route_entities or {}, tool_args={},
        confirmation_prompt=None, source="keyword"
    )
    with patch("src.rico_chat_api.get_profile", return_value=profile), \
         patch("src.rico_chat_api.is_onboarding_complete", return_value=True), \
         patch("src.rico_chat_api.upsert_profile", return_value=profile), \
         patch("src.rico_chat_api._route", return_value=route_mock):
        return api._handle_active_user("test-user", message)


# ══════════════════════════════════════════════════════════════════════════════
# A. CV profile + "Senior HSE Manager" → role_confirmation, no run_for_profile
# ══════════════════════════════════════════════════════════════════════════════

class TestA_SeniorHSEManagerConfirmation:
    def test_returns_role_confirmation(self):
        api = _make_api()
        result = _run_with_profile(api, "Senior HSE Manager", _cv_profile())
        assert result["type"] == "role_confirmation"

    def test_run_for_profile_not_called(self):
        api = _make_api()
        _run_with_profile(api, "Senior HSE Manager", _cv_profile())
        api.system.run_for_profile.assert_not_called()

    def test_role_field_correct(self):
        api = _make_api()
        result = _run_with_profile(api, "Senior HSE Manager", _cv_profile())
        assert "Senior HSE Manager" in result["role"]


# ══════════════════════════════════════════════════════════════════════════════
# B. CV profile + "Senior HSE Officer" → role_confirmation, no run_for_profile
# ══════════════════════════════════════════════════════════════════════════════

class TestB_SeniorHSEOfficerConfirmation:
    def test_returns_role_confirmation(self):
        api = _make_api()
        profile = _cv_profile(target_roles=["Senior HSE Officer"])
        result = _run_with_profile(api, "Senior HSE Officer", profile)
        assert result["type"] == "role_confirmation"

    def test_run_for_profile_not_called(self):
        api = _make_api()
        profile = _cv_profile(target_roles=["Senior HSE Officer"])
        _run_with_profile(api, "Senior HSE Officer", profile)
        api.system.run_for_profile.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# C. CV profile + "find live jobs for Senior HSE Manager" → run_for_profile called
# ══════════════════════════════════════════════════════════════════════════════

class TestC_FindLiveJobs:
    def test_run_for_profile_called(self):
        api = _make_api()
        _run_with_profile(
            api, "find live jobs for Senior HSE Manager", _cv_profile(),
            route_entities={"job_title": "Senior HSE Manager"}
        )
        api.system.run_for_profile.assert_called_once()

    def test_does_not_return_role_confirmation(self):
        api = _make_api()
        result = _run_with_profile(api, "find live jobs for Senior HSE Manager", _cv_profile())
        assert result.get("type") != "role_confirmation"


# ══════════════════════════════════════════════════════════════════════════════
# D. CV profile + "find UAE jobs for Senior HSE Manager" → run_for_profile called
# ══════════════════════════════════════════════════════════════════════════════

class TestD_FindUAEJobs:
    def test_run_for_profile_called(self):
        api = _make_api()
        _run_with_profile(
            api, "find UAE jobs for Senior HSE Manager", _cv_profile(),
            route_entities={"job_title": "Senior HSE Manager"}
        )
        api.system.run_for_profile.assert_called_once()

    def test_does_not_return_role_confirmation(self):
        api = _make_api()
        result = _run_with_profile(api, "find UAE jobs for Senior HSE Manager", _cv_profile())
        assert result.get("type") != "role_confirmation"


# ══════════════════════════════════════════════════════════════════════════════
# E. CV profile + "show current openings for Senior HSE Manager" → run_for_profile called
# ══════════════════════════════════════════════════════════════════════════════

class TestE_ShowCurrentOpenings:
    def test_run_for_profile_called(self):
        api = _make_api()
        _run_with_profile(
            api, "show current openings for Senior HSE Manager", _cv_profile(),
            route_entities={"job_title": "Senior HSE Manager"}
        )
        api.system.run_for_profile.assert_called_once()

    def test_is_live_search_detection(self):
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI._is_live_job_search_request(
            "show current openings for Senior HSE Manager"
        )


# ══════════════════════════════════════════════════════════════════════════════
# F. CV profile + "am looking for job" → profile_role_suggestions, no run_for_profile
# ══════════════════════════════════════════════════════════════════════════════

class TestF_AmLookingForJob:
    def test_returns_profile_role_suggestions(self):
        api = _make_api()
        result = _run_with_profile(api, "am looking for job", _cv_profile())
        assert result["type"] == "profile_role_suggestions"

    def test_run_for_profile_not_called(self):
        api = _make_api()
        _run_with_profile(api, "am looking for job", _cv_profile())
        api.system.run_for_profile.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# G. CV profile + "show me jobs" → profile_role_suggestions, no run_for_profile
# ══════════════════════════════════════════════════════════════════════════════

class TestG_ShowMeJobs:
    def test_returns_profile_role_suggestions(self):
        api = _make_api()
        result = _run_with_profile(api, "show me jobs", _cv_profile())
        assert result["type"] == "profile_role_suggestions"

    def test_run_for_profile_not_called(self):
        api = _make_api()
        _run_with_profile(api, "show me jobs", _cv_profile())
        api.system.run_for_profile.assert_not_called()

    def test_generic_detection(self):
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI._looks_like_generic_job_request("show me jobs")


# ══════════════════════════════════════════════════════════════════════════════
# H. CV profile + "find me jobs" → profile_role_suggestions, no run_for_profile
# ══════════════════════════════════════════════════════════════════════════════

class TestH_FindMeJobs:
    def test_returns_profile_role_suggestions(self):
        api = _make_api()
        result = _run_with_profile(api, "find me jobs", _cv_profile())
        assert result["type"] == "profile_role_suggestions"

    def test_run_for_profile_not_called(self):
        api = _make_api()
        _run_with_profile(api, "find me jobs", _cv_profile())
        api.system.run_for_profile.assert_not_called()

    def test_generic_detection(self):
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI._looks_like_generic_job_request("find me jobs")


# ══════════════════════════════════════════════════════════════════════════════
# I. No CV profile + "Senior HSE Manager" → does NOT force role_confirmation
# ══════════════════════════════════════════════════════════════════════════════

class TestI_NoCVProfile:
    def test_no_role_confirmation_without_cv(self):
        api = _make_api()
        no_cv_profile = {
            "cv_status": None,
            "cv_filename": None,
            "skills": [],
            "certifications": [],
            "years_experience": None,
            "target_roles": [],
        }
        result = _run_with_profile(api, "Senior HSE Manager", no_cv_profile)
        assert result.get("type") != "role_confirmation"

    def test_has_cv_profile_false_for_empty(self):
        from src.rico_chat_api import RicoChatAPI
        assert not RicoChatAPI._has_cv_profile({
            "cv_status": None,
            "cv_filename": None,
            "skills": [],
        })

    def test_has_cv_profile_true_for_skills(self):
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI._has_cv_profile({"skills": ["HSE"]})


# ══════════════════════════════════════════════════════════════════════════════
# J. next_actions contain action + label + message + role
# ══════════════════════════════════════════════════════════════════════════════

class TestJ_NextActionsShape:
    def _get_next_actions(self):
        api = _make_api()
        result = _run_with_profile(api, "Senior HSE Manager", _cv_profile())
        return result["next_actions"]

    def test_three_actions(self):
        actions = self._get_next_actions()
        assert len(actions) == 3

    def test_all_have_action_key(self):
        for a in self._get_next_actions():
            assert "action" in a

    def test_all_have_label_key(self):
        for a in self._get_next_actions():
            assert "label" in a

    def test_all_have_message_key(self):
        for a in self._get_next_actions():
            assert "message" in a, f"Missing 'message' in action: {a}"

    def test_all_have_role_key(self):
        for a in self._get_next_actions():
            assert "role" in a

    def test_find_live_jobs_message_triggers_pipeline(self):
        actions = self._get_next_actions()
        live_action = next(a for a in actions if a["action"] == "find_live_jobs")
        msg = live_action["message"]
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI._is_live_job_search_request(msg), (
            f"find_live_jobs message '{msg}' must trigger live search"
        )

    def test_action_keys_are_correct(self):
        actions = self._get_next_actions()
        action_keys = {a["action"] for a in actions}
        assert action_keys == {"find_live_jobs", "save_target_role", "prepare_application_angle"}

    def test_role_matches_confirmed_role(self):
        api = _make_api()
        result = _run_with_profile(api, "Senior HSE Manager", _cv_profile())
        for a in result["next_actions"]:
            assert "HSE Manager" in a["role"]


# ══════════════════════════════════════════════════════════════════════════════
# K. Acronym preservation in normalize_role_label
# ══════════════════════════════════════════════════════════════════════════════

class TestK_AcronymPreservation:
    def test_senior_hse_manager(self):
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI.normalize_role_label("senior hse manager") == "Senior HSE Manager"

    def test_qhse_coordinator(self):
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI.normalize_role_label("qhse coordinator") == "QHSE Coordinator"

    def test_esg_manager(self):
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI.normalize_role_label("esg manager") == "ESG Manager"

    def test_iso_specialist(self):
        from src.rico_chat_api import RicoChatAPI
        assert RicoChatAPI.normalize_role_label("iso 14001 specialist") == "ISO 14001 Specialist"

    def test_uae_preserved(self):
        from src.rico_chat_api import RicoChatAPI
        result = RicoChatAPI.normalize_role_label("uae operations manager")
        assert "UAE" in result

    def test_nebosh_preserved(self):
        from src.rico_chat_api import RicoChatAPI
        result = RicoChatAPI.normalize_role_label("nebosh certified officer")
        assert "NEBOSH" in result


# ══════════════════════════════════════════════════════════════════════════════
# Extra: guard tests (question mark, action words)
# ══════════════════════════════════════════════════════════════════════════════

class TestGuards:
    def test_question_mark_blocks_selection(self):
        api = _make_api()
        profile = _cv_profile()
        assert not api._looks_like_selected_role("HSE Manager?", profile)

    def test_action_word_find_blocks_selection(self):
        api = _make_api()
        profile = _cv_profile()
        assert not api._looks_like_selected_role("find HSE Manager", profile)

    def test_action_word_search_blocks_selection(self):
        api = _make_api()
        profile = _cv_profile()
        assert not api._looks_like_selected_role("search HSE Manager", profile)

    def test_action_word_show_blocks_selection(self):
        api = _make_api()
        profile = _cv_profile()
        assert not api._looks_like_selected_role("show HSE Manager", profile)


# ══════════════════════════════════════════════════════════════════════════════
# Extra: reasons quality
# ══════════════════════════════════════════════════════════════════════════════

class TestReasonsQuality:
    def _reasons(self, **profile_kwargs):
        api = _make_api()
        profile = _cv_profile(**profile_kwargs)
        result = _run_with_profile(api, "Senior HSE Manager", profile)
        return result["reasons"]

    def test_iso_reason_appears_for_iso_skill(self):
        reasons = self._reasons(skills=["ISO 14001", "Audit"])
        combined = " ".join(reasons).lower()
        assert "iso" in combined or "audit" in combined or "compliance" in combined

    def test_nebosh_reason_appears_for_nebosh_cert(self):
        reasons = self._reasons(certifications=["NEBOSH IGC"])
        combined = " ".join(reasons).lower()
        assert "nebosh" in combined or "safety" in combined or "certif" in combined

    def test_environmental_reason_appears(self):
        reasons = self._reasons(skills=["Environmental Management", "ESG"])
        combined = " ".join(reasons).lower()
        assert "environmental" in combined or "esg" in combined or "sustainability" in combined

    def test_senior_experience_reason_for_10_years(self):
        reasons = self._reasons(years_experience=12)
        combined = " ".join(reasons).lower()
        assert "senior" in combined

    def test_experienced_reason_for_5_to_9_years(self):
        reasons = self._reasons(years_experience=6)
        combined = " ".join(reasons).lower()
        assert "experienced" in combined or "professional" in combined

    def test_years_as_string_handled_safely(self):
        reasons = self._reasons(years_experience="7")
        assert len(reasons) >= 1

    def test_years_as_none_handled_safely(self):
        reasons = self._reasons(years_experience=None)
        assert len(reasons) >= 1

    def test_years_as_invalid_string_handled_safely(self):
        reasons = self._reasons(years_experience="unknown")
        assert len(reasons) >= 1

    def test_fallback_reason_when_no_data(self):
        reasons = self._reasons(
            skills=[], certifications=[], years_experience=None, industries=[]
        )
        assert len(reasons) >= 1
        assert "aligns" in reasons[0].lower() or "profile" in reasons[0].lower()


# ══════════════════════════════════════════════════════════════════════════════
# I. CV profile + follow-up "so?" / "what now?" → instant options, no pipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestI_NextStepFollowup:
    def test_so_returns_options(self):
        api = _make_api()
        result = _run_with_profile(api, "so?", _cv_profile())
        assert result["type"] == "options"

    def test_what_now_returns_options(self):
        api = _make_api()
        result = _run_with_profile(api, "what now?", _cv_profile())
        assert result["type"] == "options"

    def test_next_returns_options(self):
        api = _make_api()
        result = _run_with_profile(api, "next?", _cv_profile())
        assert result["type"] == "options"

    def test_run_for_profile_not_called(self):
        api = _make_api()
        _run_with_profile(api, "so?", _cv_profile())
        api.system.run_for_profile.assert_not_called()

    def test_options_include_message_field(self):
        api = _make_api()
        result = _run_with_profile(api, "so?", _cv_profile())
        opts = result.get("options", [])
        assert any("message" in opt for opt in opts)

    def test_no_cv_does_not_crash(self):
        api = _make_api()
        result = _run_with_profile(api, "so?", _empty_profile())
        assert result.get("type") != "options"

    def test_ok_returns_options(self):
        api = _make_api()
        result = _run_with_profile(api, "ok", _cv_profile())
        assert result["type"] == "options"

    def test_continue_returns_options(self):
        api = _make_api()
        result = _run_with_profile(api, "continue", _cv_profile())
        assert result["type"] == "options"

