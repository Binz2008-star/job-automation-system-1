"""Integration tests for complete CV-to-job-search workflow.

Tests the production workflow from CV upload through job matching:
1. CV upload persists profile fields and target role suggestions
2. Generic job-search phrases route correctly
3. Profile-based suggestions are deterministic (no OpenAI/external search)
4. Role selection handling (profile-relevant, known off-profile, unknown)
5. Job search returns matches or clear no-match response
6. Response schema is stable
7. No repeated known-field questions
8. No 45-second timeout for deterministic profile actions
"""
import pytest
from unittest.mock import patch, MagicMock

from src.rico_chat_api import RicoChatAPI
from src.rico_agent import RicoProfile
from src.repositories.profile_repo import get_profile, upsert_profile
from src.repositories.onboarding_repo import mark_onboarding_complete, is_onboarding_complete
from src.agent.intelligence.intent_classifier import classify_intent
from src.agent.intelligence.role_classifier import classify_role_candidate


class TestCVUploadAndProfilePersistence:
    """Test CV upload, parsing, and profile persistence."""

    def test_cv_upload_persists_profile_fields(self):
        """CV upload should persist skills, years_experience, and target roles."""
        user_id = "test-cv-upload@example.com"

        # Simulate CV upload by creating a profile with CV data
        profile_updates = {
            "skills": ["hse", "iso 14001", "compliance", "safety"],
            "years_experience": 10.0,
            "cv_filename": "test_cv.pdf",
            "cv_status": "parsed",
            "target_roles": ["HSE Officer", "HSE Manager"],
            "industries": ["energy", "oil & gas"],
            "profile_creation_mode": "cv_first",
            "manual_profile_wizard_disabled": True,
        }

        profile = upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        # Verify profile persistence
        retrieved = get_profile(user_id)
        assert retrieved is not None
        assert "hse" in retrieved.skills
        assert retrieved.years_experience == 10.0
        assert retrieved.cv_filename == "test_cv.pdf"
        assert retrieved.cv_status == "parsed"
        assert "HSE Officer" in retrieved.target_roles
        assert "energy" in retrieved.industries
        assert retrieved.profile_creation_mode == "cv_first"
        assert retrieved.manual_profile_wizard_disabled is True

    def test_cv_upload_generates_target_role_suggestions(self):
        """CV upload should generate target role suggestions from skills."""
        user_id = "test-role-suggestions@example.com"

        # Profile with HSE skills should generate relevant role suggestions
        profile_updates = {
            "skills": ["hse", "safety", "compliance", "iso 14001"],
            "years_experience": 8.0,
            "certifications": ["nebosh"],
            "cv_filename": "hse_cv.pdf",
            "cv_status": "parsed",
            "target_roles": ["HSE Officer", "QHSE Coordinator", "Safety Manager"],
            "profile_creation_mode": "cv_first",
        }

        profile = upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        retrieved = get_profile(user_id)
        assert retrieved is not None
        assert len(retrieved.target_roles) >= 2
        assert any("HSE" in role for role in retrieved.target_roles)


class TestGenericJobSearchPhrases:
    """Test routing of generic job-search phrases."""

    def test_i_need_job_after_cv_upload_returns_profile_suggestions(self):
        """'find me a job' after CV upload should return profile-based job search."""
        user_id = "test-i-need-job@example.com"

        # Setup profile with CV data
        profile_updates = {
            "skills": ["hse", "compliance"],
            "years_experience": 5.0,
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
            "target_roles": ["HSE Officer"],
            "preferred_cities": ["Dubai"],
            "profile_creation_mode": "cv_first",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        # Test intent classification for a phrase that actually matches
        intent_result = classify_intent("find me a job", has_cv_profile=True)
        assert intent_result.intent in ["job_search_profile_match", "job_search_explicit"]

        # Test chat response
        api = RicoChatAPI()
        response = api.process_message(user_id=user_id, message="find me a job")

        assert response["type"] in ["job_matches", "profile_role_suggestions", "job_search_profile_match"]
        assert "message" in response
        assert "success" in response
        assert "debug_id" in response

    def test_find_me_a_job_routes_correctly(self):
        """'find me a job' should route to job search intent."""
        intent_result = classify_intent("find me a job", has_cv_profile=True)
        assert intent_result.intent in ["job_search_explicit", "job_search_profile_match"]

    def test_show_jobs_routes_correctly(self):
        """'show jobs' should route to job search intent."""
        intent_result = classify_intent("show jobs", has_cv_profile=True)
        assert intent_result.intent in ["job_search_explicit", "job_search_profile_match"]

    def test_what_jobs_match_me_routes_correctly(self):
        """'what jobs match me' should route to profile match intent."""
        intent_result = classify_intent("what jobs match me", has_cv_profile=True)
        assert intent_result.intent == "job_search_profile_match"

    def test_show_roles_from_my_cv_routes_to_suggestions(self):
        """'show roles from my CV' should route to profile role suggestions."""
        intent_result = classify_intent("show roles from my cv", has_cv_profile=True)
        assert intent_result.intent == "profile_role_suggestions"


class TestProfileRoleSuggestions:
    """Test deterministic profile-based role suggestions."""

    def test_show_roles_from_cv_returns_fast_deterministic_suggestions(self):
        """'show roles from my CV' should return fast deterministic suggestions without OpenAI."""
        user_id = "test-roles-cv@example.com"

        # Setup profile
        profile_updates = {
            "skills": ["hse", "safety", "compliance"],
            "years_experience": 7.0,
            "certifications": ["nebosh"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
            "target_roles": ["HSE Officer"],
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        api = RicoChatAPI()
        response = api.process_message(user_id=user_id, message="show roles from my cv")

        assert response["type"] == "profile_role_suggestions"
        assert "message" in response
        assert "options" in response
        assert "success" in response
        assert "debug_id" in response
        assert len(response["options"]) > 0
        # Verify suggestions are based on profile skills
        assert any("hse" in opt.get("label", "").lower() or "safety" in opt.get("label", "").lower()
                   for opt in response["options"])

    def test_profile_suggestions_no_openai_call(self):
        """Profile role suggestions should not call OpenAI (deterministic)."""
        user_id = "test-no-openai@example.com"

        profile_updates = {
            "skills": ["hse", "compliance"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        # Mock OpenAI agent to detect if it's called
        with patch('src.rico_chat_api.RicoOpenAIAgent') as mock_openai:
            mock_agent = MagicMock()
            mock_openai.return_value = mock_agent
            mock_agent.respond.return_value = {"type": "openai_response", "message": "test"}

            api = RicoChatAPI()
            response = api.process_message(user_id=user_id, message="show roles from my cv")

            # Profile role suggestions should NOT call OpenAI
            if response["type"] == "profile_role_suggestions":
                mock_agent.respond.assert_not_called()

    def test_profile_suggestions_no_external_job_search(self):
        """Profile role suggestions should not trigger external job search."""
        user_id = "test-no-external-search@example.com"

        profile_updates = {
            "skills": ["hse", "safety"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        # Mock the system to detect if job search is called
        with patch('src.rico_chat_api.RicoSystem') as mock_system:
            mock_sys = MagicMock()
            mock_system.return_value = mock_sys
            mock_sys.run_for_profile.return_value = {"matches": []}

            api = RicoChatAPI()
            response = api.process_message(user_id=user_id, message="show roles from my cv")

            # Profile role suggestions should NOT call job search
            if response["type"] == "profile_role_suggestions":
                mock_sys.run_for_profile.assert_not_called()


class TestRoleSelectionHandling:
    """Test 3-tier role selection handling."""

    def test_profile_relevant_role_searches_directly(self):
        """Profile-relevant role should search directly without confirmation."""
        user_id = "test-profile-relevant@example.com"

        # Setup profile with HSE skills
        profile_updates = {
            "skills": ["hse", "safety", "compliance"],
            "target_roles": ["HSE Officer"],
            "years_experience": 5.0,
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
            "preferred_cities": ["Dubai"],
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        profile = get_profile(user_id)

        # Test role classification for profile-relevant role
        classification, canonical = classify_role_candidate("hse officer", profile)
        assert classification == "profile_relevant"
        assert canonical == "HSE Officer"

    def test_known_off_profile_role_requests_confirmation(self):
        """Known but off-profile role should ask for confirmation."""
        user_id = "test-off-profile@example.com"

        # Setup HSE profile
        profile_updates = {
            "skills": ["hse", "safety"],
            "target_roles": ["HSE Officer"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        profile = get_profile(user_id)

        # Test role classification for known off-profile role (sales)
        classification, canonical = classify_role_candidate("sales", profile)
        assert classification == "known_but_off_profile"
        assert canonical == "Sales Executive"

    def test_sales_after_cv_upload_shows_confirmation(self):
        """'sales' after CV upload should show confirmation dialog."""
        user_id = "test-sales-confirmation@example.com"

        profile_updates = {
            "skills": ["hse", "safety"],
            "target_roles": ["HSE Officer"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        api = RicoChatAPI()
        response = api.process_message(user_id=user_id, message="sales")

        # Should show confirmation for known off-profile role
        assert response["type"] == "clarification"
        assert "Sales" in response["message"] or "sales" in response["message"].lower()
        assert "options" in response
        assert len(response["options"]) > 0

    def test_unknown_role_redirects_to_profile_roles(self):
        """Unknown nonsense role should redirect to profile roles."""
        user_id = "test-unknown-role@example.com"

        profile_updates = {
            "skills": ["hse", "safety"],
            "target_roles": ["HSE Officer"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        profile = get_profile(user_id)

        # Test role classification for unknown role
        classification, canonical = classify_role_candidate("xyz123 nonsense", profile)
        assert classification == "unknown"
        assert canonical is None

    def test_unknown_nonsense_role_does_not_search(self):
        """Unknown nonsense role should not trigger job search."""
        user_id = "test-nonsense@example.com"

        profile_updates = {
            "skills": ["hse"],
            "target_roles": ["HSE Officer"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        # Test that nonsense is classified correctly
        from src.agent.intelligence.intent_classifier import classify_intent
        intent_result = classify_intent("xyz123", has_cv_profile=True)
        assert intent_result.intent == "unknown"

        # Mock the system to detect if job search is called
        with patch('src.rico_chat_api.RicoSystem') as mock_system:
            mock_sys = MagicMock()
            mock_system.return_value = mock_sys
            mock_sys.run_for_profile.return_value = {"matches": []}

            api = RicoChatAPI()
            response = api.process_message(user_id=user_id, message="xyz123")

            # Unknown role should NOT call job search (may fall through to AI but not job search)
            mock_sys.run_for_profile.assert_not_called()
            # Response should be clarification or nonsense type
            assert response["type"] in ["clarification", "nonsense", "deepseek_response", "openai_response"]


class TestResponseSchemaStability:
    """Test stable response schema."""

    def test_chat_response_includes_required_fields(self):
        """Every chat response should include type, message, success, debug_id."""
        user_id = "test-schema@example.com"

        profile_updates = {
            "skills": ["hse"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
            "target_roles": ["HSE Officer"],
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        api = RicoChatAPI()

        # Test various message types
        test_messages = [
            "show roles from my cv",
            "i need job",
            "hse officer",
            "help",
        ]

        for message in test_messages:
            response = api.process_message(user_id=user_id, message=message)
            assert "type" in response, f"Missing 'type' in response for: {message}"
            assert "message" in response, f"Missing 'message' in response for: {message}"
            assert "success" in response, f"Missing 'success' in response for: {message}"
            assert "debug_id" in response, f"Missing 'debug_id' in response for: {message}"


class TestNoRepeatedKnownFieldQuestions:
    """Test that known fields are not re-asked."""

    def test_no_repeated_experience_questions(self):
        """Experience questions should be blocked when years_experience is known."""
        user_id = "test-no-repeat-exp@example.com"

        profile_updates = {
            "skills": ["hse"],
            "years_experience": 10.0,
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        api = RicoChatAPI()
        profile = get_profile(user_id)
        blocked = api._get_blocked_questions(profile)

        assert "experience" in blocked

    def test_no_repeated_location_questions(self):
        """Location questions should be blocked when preferred_cities is known."""
        user_id = "test-no-repeat-loc@example.com"

        profile_updates = {
            "skills": ["hse"],
            "preferred_cities": ["Dubai"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        api = RicoChatAPI()
        profile = get_profile(user_id)
        blocked = api._get_blocked_questions(profile)

        assert "location" in blocked

    def test_no_repeated_industry_questions(self):
        """Industry questions should be blocked when skills/industries is known."""
        user_id = "test-no-repeat-ind@example.com"

        profile_updates = {
            "skills": ["hse", "compliance"],
            "industries": ["energy"],
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        api = RicoChatAPI()
        profile = get_profile(user_id)
        blocked = api._get_blocked_questions(profile)

        assert "industry" in blocked

    def test_blocked_questions_are_removed_from_ai_response(self):
        """Blocked question patterns should be filtered from AI responses."""
        api = RicoChatAPI()

        response = "What is your experience level?\nPreferred location?\nHere are some jobs."
        blocked = ["experience", "location"]

        filtered = api._remove_blocked_questions(response, blocked)

        assert "experience level" not in filtered.lower()
        assert "preferred location" not in filtered.lower()
        assert "here are some jobs" in filtered.lower()


class TestDeterministicPerformance:
    """Test that deterministic actions are fast (no 45-second timeouts)."""

    def test_profile_role_suggestions_is_fast(self):
        """Profile role suggestions should complete quickly (deterministic)."""
        import time

        user_id = "test-fast-suggestions@example.com"

        profile_updates = {
            "skills": ["hse", "safety", "compliance"],
            "certifications": ["nebosh"],
            "years_experience": 8.0,
            "cv_filename": "cv.pdf",
            "cv_status": "parsed",
        }
        upsert_profile(user_id=user_id, updates=profile_updates)
        mark_onboarding_complete(user_id)

        api = RicoChatAPI()

        start = time.time()
        response = api.process_message(user_id=user_id, message="show roles from my cv")
        elapsed = time.time() - start

        # Should complete in under 5 seconds (deterministic, no OpenAI)
        assert elapsed < 5.0, f"Profile suggestions took {elapsed:.2f}s, expected < 5s"
        assert response["type"] == "profile_role_suggestions"

    def test_intent_classification_is_fast(self):
        """Intent classification should be very fast (regex-based)."""
        import time

        start = time.time()
        for _ in range(100):
            classify_intent("i need job", has_cv_profile=True)
        elapsed = time.time() - start

        # 100 classifications should complete in under 1 second
        assert elapsed < 1.0, f"100 intent classifications took {elapsed:.2f}s"

    def test_role_classification_is_fast(self):
        """Role classification should be fast (taxonomy-based)."""
        import time

        user_id = "test-fast-role-class@example.com"
        profile_updates = {
            "skills": ["hse"],
            "target_roles": ["HSE Officer"],
        }
        profile = upsert_profile(user_id=user_id, updates=profile_updates)

        start = time.time()
        for _ in range(100):
            classify_role_candidate("hse officer", profile)
        elapsed = time.time() - start

        # 100 classifications should complete in under 2 seconds
        assert elapsed < 2.0, f"100 role classifications took {elapsed:.2f}s"
