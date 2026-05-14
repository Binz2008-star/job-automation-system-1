"""tests/unit/test_cv_persistence_chat.py

Regression tests for Issue #101: public CV profile persistence so chat
stops re-asking known fields.

Covers:
- RicoProfile dataclass preserves CV fields (cv_filename, cv_status, etc.)
- _has_cv_profile detects CV-backed profiles correctly
- _looks_like_bare_target_role is case-insensitive
- _get_blocked_questions blocks experience/location/industry when known
- _remove_blocked_questions strips blocked lines from AI responses
"""
import pytest

from src.rico_agent import RicoProfile
from src.rico_chat_api import RicoChatAPI


class TestRicoProfileCVFields:
    """RicoProfile must accept and round-trip CV-related fields."""

    def test_cv_filename_preserved(self):
        profile = RicoProfile(
            user_id="test@example.com",
            cv_filename="cv_test.pdf",
        )
        assert profile.cv_filename == "cv_test.pdf"

    def test_cv_status_preserved(self):
        profile = RicoProfile(
            user_id="test@example.com",
            cv_status="parsed",
        )
        assert profile.cv_status == "parsed"

    def test_profile_creation_mode_preserved(self):
        profile = RicoProfile(
            user_id="test@example.com",
            profile_creation_mode="cv_first",
        )
        assert profile.profile_creation_mode == "cv_first"

    def test_manual_profile_wizard_disabled_preserved(self):
        profile = RicoProfile(
            user_id="test@example.com",
            manual_profile_wizard_disabled=True,
        )
        assert profile.manual_profile_wizard_disabled is True

    def test_full_cv_profile_roundtrip(self):
        profile = RicoProfile(
            user_id="public:web-test",
            cv_filename="robin_cv.pdf",
            cv_status="parsed",
            skills=["hse", "iso 14001", "compliance"],
            years_experience=10.0,
            profile_creation_mode="cv_first",
            manual_profile_wizard_disabled=True,
        )
        assert profile.cv_filename == "robin_cv.pdf"
        assert profile.cv_status == "parsed"
        assert profile.skills == ["hse", "iso 14001", "compliance"]
        assert profile.years_experience == 10.0


class TestHasCvProfile:
    """_has_cv_profile must detect CV-backed profiles via any reliable signal."""

    def test_none_profile_returns_false(self):
        assert RicoChatAPI._has_cv_profile(None) is False

    def test_cv_filename_signal(self):
        profile = RicoProfile(user_id="u1", cv_filename="cv.pdf")
        assert RicoChatAPI._has_cv_profile(profile) is True

    def test_cv_status_parsed_signal(self):
        profile = RicoProfile(user_id="u1", cv_status="parsed")
        assert RicoChatAPI._has_cv_profile(profile) is True

    def test_skills_signal(self):
        profile = RicoProfile(user_id="u1", skills=["python"])
        assert RicoChatAPI._has_cv_profile(profile) is True

    def test_years_experience_signal(self):
        profile = RicoProfile(user_id="u1", years_experience=5.0)
        assert RicoChatAPI._has_cv_profile(profile) is True

    def test_empty_profile_returns_false(self):
        profile = RicoProfile(user_id="u1")
        assert RicoChatAPI._has_cv_profile(profile) is False

    def test_dict_profile_cv_status(self):
        assert RicoChatAPI._has_cv_profile({"cv_status": "parsed"}) is True

    def test_dict_profile_empty(self):
        assert RicoChatAPI._has_cv_profile({}) is False


class TestLooksLikeBareTargetRole:
    """_looks_like_bare_target_role must accept lowercase role names."""

    @pytest.mark.parametrize("message", [
        "sales man",
        "Sales Man",
        "SALES MAN",
        "software engineer",
        "hse manager",
        "general manager",
        "product owner",
        "data scientist",
    ])
    def test_lowercase_roles_are_accepted(self, message):
        assert RicoChatAPI._looks_like_bare_target_role(message) is True

    def test_whats_next_phrases_rejected(self):
        assert RicoChatAPI._looks_like_bare_target_role("what's next") is False

    def test_digits_rejected(self):
        assert RicoChatAPI._looks_like_bare_target_role("sales manager 2") is False

    def test_too_many_words_rejected(self):
        assert RicoChatAPI._looks_like_bare_target_role("this is a very long role name") is False

    def test_empty_rejected(self):
        assert RicoChatAPI._looks_like_bare_target_role("") is False


class TestGetBlockedQuestions:
    """_get_blocked_questions must block questions for fields already known from CV."""

    def test_no_profile_returns_empty(self):
        api = RicoChatAPI()
        assert api._get_blocked_questions(None) == []

    def test_cv_filename_blocks_experience(self):
        api = RicoChatAPI()
        profile = RicoProfile(user_id="u1", cv_filename="cv.pdf")
        blocked = api._get_blocked_questions(profile)
        assert "experience" in blocked

    def test_cv_status_parsed_blocks_experience(self):
        api = RicoChatAPI()
        profile = RicoProfile(user_id="u1", cv_status="parsed")
        blocked = api._get_blocked_questions(profile)
        assert "experience" in blocked

    def test_years_experience_blocks_experience(self):
        api = RicoChatAPI()
        profile = RicoProfile(user_id="u1", years_experience=8.0)
        blocked = api._get_blocked_questions(profile)
        assert "experience" in blocked

    def test_preferred_cities_blocks_location(self):
        api = RicoChatAPI()
        profile = RicoProfile(user_id="u1", preferred_cities=["Dubai"])
        blocked = api._get_blocked_questions(profile)
        assert "location" in blocked

    def test_dict_cities_blocks_location(self):
        api = RicoChatAPI()
        profile = {"cities": ["Abu Dhabi"]}
        blocked = api._get_blocked_questions(profile)
        assert "location" in blocked

    def test_skills_blocks_industry(self):
        api = RicoChatAPI()
        profile = RicoProfile(user_id="u1", skills=["python", "sql"])
        blocked = api._get_blocked_questions(profile)
        assert "industry" in blocked

    def test_empty_skills_do_not_block_industry(self):
        api = RicoChatAPI()
        profile = RicoProfile(user_id="u1", skills=[])
        blocked = api._get_blocked_questions(profile)
        assert "industry" not in blocked

    def test_industries_blocks_industry(self):
        api = RicoChatAPI()
        profile = RicoProfile(user_id="u1", industries=["technology"])
        blocked = api._get_blocked_questions(profile)
        assert "industry" in blocked

    def test_full_cv_profile_blocks_all_three(self):
        api = RicoChatAPI()
        profile = RicoProfile(
            user_id="u1",
            cv_filename="cv.pdf",
            cv_status="parsed",
            skills=["hse", "compliance"],
            years_experience=10.0,
            preferred_cities=["Dubai"],
            industries=["energy"],
        )
        blocked = api._get_blocked_questions(profile)
        assert "experience" in blocked
        assert "location" in blocked
        assert "industry" in blocked


class TestRemoveBlockedQuestions:
    """_remove_blocked_questions must strip lines containing blocked patterns."""

    def test_filters_experience_level_line(self):
        api = RicoChatAPI()
        response = "What is your experience level?\nHere are some jobs."
        result = api._remove_blocked_questions(response, ["experience"])
        assert "experience level" not in result
        assert "Here are some jobs." in result

    def test_filters_years_of_experience_line(self):
        api = RicoChatAPI()
        response = "How many years of experience do you have?\nGreat!"
        result = api._remove_blocked_questions(response, ["experience"])
        assert "years of experience" not in result

    def test_filters_location_line(self):
        api = RicoChatAPI()
        response = "What city do you prefer?\nI found jobs."
        result = api._remove_blocked_questions(response, ["location"])
        assert "city" not in result
        assert "I found jobs." in result

    def test_filters_industry_line(self):
        api = RicoChatAPI()
        response = "Which industry are you targeting?\nHere you go."
        result = api._remove_blocked_questions(response, ["industry"])
        assert "industry" not in result

    def test_no_blocked_returns_original(self):
        api = RicoChatAPI()
        response = "What type of sales?"
        result = api._remove_blocked_questions(response, [])
        assert result == response

    def test_empty_response_returns_empty(self):
        api = RicoChatAPI()
        assert api._remove_blocked_questions("", ["experience"]) == ""

    def test_multiline_filters_multiple_blocked(self):
        api = RicoChatAPI()
        response = (
            "What type of sales?\n"
            "Preferred location?\n"
            "Experience level?\n"
            "Here are matching jobs."
        )
        blocked = ["experience", "location"]
        result = api._remove_blocked_questions(response, blocked)
        assert "Experience level" not in result
        assert "Preferred location" not in result
        assert "What type of sales" in result
        assert "Here are matching jobs." in result
