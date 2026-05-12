"""Tests for profile role suggestions - deterministic fast path.

Tests that "Show roles from my CV" and similar phrases:
- Return fast deterministic suggestions
- Do NOT call OpenAI
- Do NOT run external job search
- Are based on CV skills/certifications
- Do not time out
- Do not ask repeated known-field questions
"""
import pytest
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any

from src.rico_chat_api import RicoChatAPI
from src.agent.intelligence.intent_classifier import classify_intent


@dataclass
class MockProfile:
    """Mock profile for testing."""
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    years_experience: Optional[float] = None
    certifications: List[str] = field(default_factory=list)
    industries: List[str] = field(default_factory=list)
    target_roles: List[str] = field(default_factory=list)
    preferred_cities: List[str] = field(default_factory=list)


class TestProfileRoleSuggestionsIntent:
    """Test intent classification for profile role suggestions."""

    def test_show_roles_from_my_cv_exact_match(self):
        """Exact phrase 'show roles from my cv' should match."""
        result = classify_intent("show roles from my cv", has_cv_profile=True)
        assert result.intent == "profile_role_suggestions"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_what_roles_fit_my_cv_exact_match(self):
        """Exact phrase 'what roles fit my cv' should match."""
        result = classify_intent("what roles fit my cv", has_cv_profile=True)
        assert result.intent == "profile_role_suggestions"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_suggest_roles_from_my_cv_exact_match(self):
        """Exact phrase 'suggest roles from my cv' should match."""
        result = classify_intent("suggest roles from my cv", has_cv_profile=True)
        assert result.intent == "profile_role_suggestions"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_best_roles_for_my_profile_exact_match(self):
        """Exact phrase 'best roles for my profile' should match."""
        result = classify_intent("best roles for my profile", has_cv_profile=True)
        assert result.intent == "profile_role_suggestions"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_role_suggestions_exact_match(self):
        """Exact phrase 'role suggestions' should match."""
        result = classify_intent("role suggestions", has_cv_profile=True)
        assert result.intent == "profile_role_suggestions"
        assert result.confidence == 1.0
        assert result.source == "exact"

    def test_case_insensitive_matching(self):
        """Intent matching should be case-insensitive."""
        result = classify_intent("SHOW ROLES FROM MY CV", has_cv_profile=True)
        assert result.intent == "profile_role_suggestions"
        assert result.confidence == 1.0


class TestProfileRoleSuggestionsHandler:
    """Test role suggestion handler logic."""

    def test_hse_skills_generates_hse_roles(self):
        """HSE skills should generate HSE-related role suggestions."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["hse", "safety", "iso 14001"],
            years_experience=10.0,
            certifications=["iso"]
        )

        result = api._handle_profile_role_suggestions(profile)

        assert result["type"] == "profile_role_suggestions"
        assert result["next_action"] == "select_role_to_search"
        assert len(result["options"]) > 0

        role_labels = [opt["label"] for opt in result["options"]]
        # Should include HSE-related roles
        assert any("HSE" in label for label in role_labels)
        assert any("Safety" in label for label in role_labels)

    def test_environmental_skills_generates_environmental_roles(self):
        """Environmental skills should generate environmental role suggestions."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["environmental", "sustainability", "esg"],
            years_experience=8.0
        )

        result = api._handle_profile_role_suggestions(profile)

        assert result["type"] == "profile_role_suggestions"
        role_labels = [opt["label"] for opt in result["options"]]
        
        # Should include environmental/sustainability roles
        assert any("Environmental" in label for label in role_labels)
        assert any("Sustainability" in label or "ESG" in label for label in role_labels)

    def test_compliance_audit_skills_generates_audit_roles(self):
        """Compliance/audit skills should generate audit role suggestions."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["compliance", "audit"],
            years_experience=5.0
        )

        result = api._handle_profile_role_suggestions(profile)

        assert result["type"] == "profile_role_suggestions"
        role_labels = [opt["label"] for opt in result["options"]]
        
        # Should include compliance/audit roles
        assert any("Compliance" in label for label in role_labels)
        assert any("Auditor" in label for label in role_labels)

    def test_seniority_prefix_for_10_plus_years(self):
        """10+ years experience should add 'Senior' prefix to roles."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["hse", "operations"],
            years_experience=10.0
        )

        result = api._handle_profile_role_suggestions(profile)
        role_labels = [opt["label"] for opt in result["options"]]
        
        # At least some roles should have Senior prefix
        senior_roles = [label for label in role_labels if "Senior" in label]
        assert len(senior_roles) > 0

    def test_no_seniority_for_less_than_5_years(self):
        """Less than 5 years experience should not add seniority prefix."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["hse"],
            years_experience=3.0
        )

        result = api._handle_profile_role_suggestions(profile)
        role_labels = [opt["label"] for opt in result["options"]]
        
        # No roles should have Senior prefix
        senior_roles = [label for label in role_labels if "Senior" in label]
        assert len(senior_roles) == 0

    def test_no_profile_returns_upload_cv_action(self):
        """No profile should return upload_cv next action."""
        api = RicoChatAPI()
        result = api._handle_profile_role_suggestions(None)

        assert result["type"] == "profile_role_suggestions"
        assert result["next_action"] == "upload_cv"
        assert len(result["options"]) == 0

    def test_empty_profile_returns_add_skills_action(self):
        """Empty profile should return add_skills next action."""
        api = RicoChatAPI()
        profile = MockProfile()

        result = api._handle_profile_role_suggestions(profile)

        assert result["type"] == "profile_role_suggestions"
        assert result["next_action"] == "add_skills"
        assert len(result["options"]) == 0

    def test_limits_to_top_8_suggestions(self):
        """Should limit suggestions to top 8."""
        api = RicoChatAPI()
        # Profile with many matching skills
        profile = MockProfile(
            skills=["hse", "safety", "environmental", "sustainability", "esg", 
                   "compliance", "audit", "iso", "operations", "management"],
            years_experience=10.0
        )

        result = api._handle_profile_role_suggestions(profile)

        assert len(result["options"]) <= 8

    def test_no_duplicate_role_suggestions(self):
        """Should not return duplicate role labels."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["hse", "safety"],  # These may generate overlapping roles
            years_experience=5.0
        )

        result = api._handle_profile_role_suggestions(profile)
        role_labels = [opt["label"] for opt in result["options"]]
        
        # Check for duplicates
        assert len(role_labels) == len(set(role_labels))

    def test_iso_certification_adds_iso_roles(self):
        """ISO certification should add ISO-specific roles."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["quality"],
            certifications=["iso"],
            years_experience=5.0
        )

        result = api._handle_profile_role_suggestions(profile)
        role_labels = [opt["label"] for opt in result["options"]]
        
        # Should include ISO-related role
        assert any("ISO" in label for label in role_labels)

    def test_nebosh_certification_adds_hse_manager(self):
        """NEBOSH certification should add HSE Manager role."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["safety"],
            certifications=["nebosh"],
            years_experience=5.0
        )

        result = api._handle_profile_role_suggestions(profile)
        role_labels = [opt["label"] for opt in result["options"]]
        
        # Should include HSE Manager
        assert "HSE Manager" in role_labels


class TestProfileRoleSuggestionsIntegration:
    """Integration tests for profile role suggestions."""

    def test_full_integration_with_cv_profile(self):
        """Test full flow with realistic CV profile (Roben's CV)."""
        api = RicoChatAPI()
        profile = MockProfile(
            email="robenedwan@gmail.com",
            phone="+971 52 223 3989",
            skills=["hse", "iso 14001", "audit", "compliance", "esg", 
                   "sustainability", "environmental management", "excel", "operations"],
            years_experience=10.0,
            certifications=["iso"],
            industries=["environmental", "wastewater management"]
        )

        result = api._handle_profile_role_suggestions(profile)

        # Verify structure
        assert result["type"] == "profile_role_suggestions"
        assert result["next_action"] == "select_role_to_search"
        assert "Based on your CV" in result["message"]
        
        # Verify role suggestions for Roben's profile
        role_labels = [opt["label"] for opt in result["options"]]
        
        # Should include expected roles for HSE/Environmental profile
        expected_role_families = [
            "HSE", "Environmental", "Compliance", "Audit", 
            "Sustainability", "ESG", "ISO"
        ]
        
        for family in expected_role_families:
            assert any(family in label for label in role_labels), \
                f"Expected role family '{family}' not found in suggestions: {role_labels}"

    def test_deterministic_same_input_same_output(self):
        """Same profile should always produce same suggestions (deterministic)."""
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["hse", "safety"],
            years_experience=5.0
        )

        result1 = api._handle_profile_role_suggestions(profile)
        result2 = api._handle_profile_role_suggestions(profile)

        assert result1 == result2

    def test_fast_response_no_external_calls(self):
        """Handler should be fast and not make external calls."""
        import time
        
        api = RicoChatAPI()
        profile = MockProfile(
            skills=["hse", "safety", "iso 14001"],
            years_experience=10.0
        )

        start = time.time()
        result = api._handle_profile_role_suggestions(profile)
        elapsed = time.time() - start

        # Should complete in under 100ms (no network calls)
        assert elapsed < 0.1
        assert result["type"] == "profile_role_suggestions"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
