"""Tests for ProfileContextResolver.

Covers:
* Normalisation from dict / object / RicoProfile / None
* Alias resolution
* Derived properties (has_cv, completion_score, missing_fields)
* Edge cases (empty strings, comma-separated strings, bad numeric input)
"""

from __future__ import annotations

import pytest

from src.rico_agent import RicoProfile
from src.services.profile_context_resolver import (
    ProfileContext,
    resolve_profile_context,
)


class TestResolveFromDict:
    def test_empty_dict_returns_minimal_context(self):
        ctx = resolve_profile_context("u1", {})
        assert ctx.user_id == "u1"
        assert ctx.skills == []
        assert ctx.has_cv is False

    def test_skills_as_list_preserved(self):
        ctx = resolve_profile_context("u1", {"skills": ["Python", "SQL"]})
        assert ctx.skills == ["Python", "SQL"]

    def test_skills_comma_string_split(self):
        ctx = resolve_profile_context("u1", {"skills": "Python, SQL, Excel"})
        assert ctx.skills == ["Python", "SQL", "Excel"]

    def test_years_experience_float(self):
        ctx = resolve_profile_context("u1", {"years_experience": "5.5"})
        assert ctx.years_experience == 5.5

    def test_salary_int_from_string(self):
        ctx = resolve_profile_context("u1", {"salary_expectation_aed": "25000"})
        assert ctx.salary_expectation_aed == 25000

    def test_alias_location(self):
        ctx = resolve_profile_context("u1", {"location": "Dubai"})
        assert ctx.current_location == "Dubai"

    def test_alias_cities(self):
        ctx = resolve_profile_context("u1", {"cities": "Dubai, Abu Dhabi"})
        assert ctx.preferred_cities == ["Dubai", "Abu Dhabi"]

    def test_alias_target_role(self):
        ctx = resolve_profile_context("u1", {"target_role": "Data Analyst"})
        assert ctx.target_roles == ["Data Analyst"]

    def test_alias_experience_years(self):
        ctx = resolve_profile_context("u1", {"experience_years": 3})
        assert ctx.years_experience == 3.0

    def test_empty_string_becomes_none(self):
        ctx = resolve_profile_context("u1", {"name": "   "})
        assert ctx.name is None


class TestResolveFromRicoProfile:
    def test_rico_profile_roundtrip(self):
        rp = RicoProfile(
            user_id="u1",
            name="Ali",
            skills=["Python"],
            years_experience=4.0,
            target_roles=["Senior Dev"],
        )
        ctx = resolve_profile_context("u1", rp)
        assert ctx.name == "Ali"
        assert ctx.skills == ["Python"]
        assert ctx.years_experience == 4.0
        assert ctx.target_roles == ["Senior Dev"]


class TestResolveFromObject:
    class FakeProfile:
        def __init__(self):
            self.skills = ["HSE"]
            self.years_experience = 8
            self.cv_status = "parsed"

    def test_object_attributes(self):
        obj = self.FakeProfile()
        ctx = resolve_profile_context("u1", obj)
        assert ctx.skills == ["HSE"]
        assert ctx.years_experience == 8.0
        assert ctx.has_cv is True


class TestResolveFromNone:
    def test_none_returns_empty(self):
        ctx = resolve_profile_context("u1", None)
        assert ctx.user_id == "u1"
        assert ctx.skills == []
        assert ctx.has_cv is False


class TestDerivedProperties:
    def test_has_cv_when_cv_status_parsed(self):
        ctx = resolve_profile_context("u1", {"cv_status": "parsed"})
        assert ctx.has_cv is True

    def test_has_cv_when_skills_present(self):
        ctx = resolve_profile_context("u1", {"skills": ["Python"]})
        assert ctx.has_cv is True

    def test_has_cv_false_when_empty(self):
        ctx = resolve_profile_context("u1", {})
        assert ctx.has_cv is False

    def test_completion_score_full(self):
        ctx = resolve_profile_context(
            "u1",
            {
                "skills": ["A"],
                "years_experience": 5,
                "target_roles": ["Dev"],
                "preferred_cities": ["Dubai"],
                "salary_expectation_aed": 10000,
                "current_role": "Junior Dev",
                "industries": ["Tech"],
            },
        )
        assert ctx.completion_score == 1.0

    def test_completion_score_half(self):
        ctx = resolve_profile_context(
            "u1", {"skills": ["A"], "years_experience": 5}
        )
        assert ctx.completion_score == 2 / 7

    def test_missing_fields(self):
        ctx = resolve_profile_context("u1", {"skills": ["A"]})
        missing = ctx.missing_fields
        assert "years_experience" in missing
        assert "skills" not in missing

    def test_is_onboarding_complete_true(self):
        ctx = resolve_profile_context(
            "u1",
            {
                "cv_status": "parsed",
                "skills": ["A"],
                "years_experience": 5,
                "target_roles": ["Dev"],
                "preferred_cities": ["Dubai"],
                "salary_expectation_aed": 10000,
                "current_role": "Dev",
                "industries": ["Tech"],
            },
        )
        assert ctx.is_onboarding_complete is True

    def test_is_onboarding_complete_false_no_cv(self):
        # No CV data at all — has_cv should be False regardless of other fields
        ctx = resolve_profile_context(
            "u1",
            {
                "target_roles": ["Dev"],
                "preferred_cities": ["Dubai"],
                "salary_expectation_aed": 10000,
                "current_role": "Dev",
                "industries": ["Tech"],
            },
        )
        assert ctx.is_onboarding_complete is False


class TestSummaryText:
    def test_summary_includes_key_fields(self):
        ctx = resolve_profile_context(
            "u1",
            {
                "current_role": "HSE Manager",
                "target_roles": ["Senior HSE Manager"],
                "years_experience": 8,
                "skills": ["HSE", "Risk Assessment", "ISO 45001"],
                "preferred_cities": ["Dubai", "Abu Dhabi"],
            },
        )
        summary = ctx.summary_text()
        assert "HSE Manager" in summary
        assert "Senior HSE Manager" in summary
        assert "8.0 yrs" in summary
        assert "Dubai" in summary

    def test_summary_truncated(self):
        ctx = resolve_profile_context(
            "u1",
            {"skills": ["S" * 100]},
        )
        summary = ctx.summary_text(max_chars=20)
        assert len(summary) <= 20


class TestDictAccess:
    def test_get_existing(self):
        ctx = resolve_profile_context("u1", {"skills": ["A"]})
        assert ctx.get("skills") == ["A"]

    def test_get_default(self):
        ctx = resolve_profile_context("u1", {})
        assert ctx.get("nonexistent", "fallback") == "fallback"

    def test_to_dict_serializable(self):
        ctx = resolve_profile_context(
            "u1", {"skills": ["A"], "years_experience": 5}
        )
        d = ctx.to_dict()
        assert d["skills"] == ["A"]
        assert d["years_experience"] == 5.0
        assert d["user_id"] == "u1"
