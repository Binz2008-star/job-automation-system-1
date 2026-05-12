"""src/agent/intelligence/scorer.py

Profile-fit scoring for Rico Agent OS.

Scores how well a user's profile matches a target role:
- Skills match (required vs optional)
- Experience level alignment
- Industry relevance
- Location preference
- Overall fit score (0.0-1.0)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from src.rico_agent import RicoProfile

logger = logging.getLogger(__name__)


@dataclass
class RoleRequirements:
    """Requirements for a target role."""
    canonical_role: str
    required_skills: Set[str] = field(default_factory=set)
    preferred_skills: Set[str] = field(default_factory=set)
    min_years_experience: Optional[float] = None
    preferred_years_experience: Optional[float] = None
    required_industries: Set[str] = field(default_factory=set)
    preferred_industries: Set[str] = field(default_factory=set)


@dataclass
class FitScore:
    """Result of profile-fit scoring."""
    overall_score: float  # 0.0-1.0
    skills_score: float  # 0.0-1.0
    experience_score: float  # 0.0-1.0
    industry_score: float  # 0.0-1.0
    location_score: float  # 0.0-1.0
    missing_required_skills: List[str] = field(default_factory=list)
    matched_required_skills: List[str] = field(default_factory=list)
    matched_preferred_skills: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


# Predefined role requirements (can be extended with AI inference)
_ROLE_REQUIREMENTS: Dict[str, RoleRequirements] = {
    "Software Engineer": RoleRequirements(
        canonical_role="Software Engineer",
        required_skills={"python", "javascript", "git", "sql"},
        preferred_skills={"docker", "kubernetes", "aws", "ci/cd", "testing"},
        min_years_experience=1.0,
        preferred_years_experience=3.0,
        required_industries=set(),
        preferred_industries={"technology", "software", "fintech", "ecommerce"},
    ),
    "Product Manager": RoleRequirements(
        canonical_role="Product Manager",
        required_skills={"product management", "agile", "user research", "roadmap"},
        preferred_skills={"data analysis", "a/b testing", "sql", "analytics", "ux"},
        min_years_experience=2.0,
        preferred_years_experience=5.0,
        required_industries=set(),
        preferred_industries={"technology", "software", "fintech", "ecommerce"},
    ),
    "Data Scientist": RoleRequirements(
        canonical_role="Data Scientist",
        required_skills={"python", "machine learning", "statistics", "sql"},
        preferred_skills={"deep learning", "nlp", "computer vision", "spark", "airflow"},
        min_years_experience=1.0,
        preferred_years_experience=3.0,
        required_industries=set(),
        preferred_industries={"technology", "fintech", "healthcare", "ecommerce"},
    ),
    "Sales Representative": RoleRequirements(
        canonical_role="Sales Representative",
        required_skills={"sales", "communication", "crm", "negotiation"},
        preferred_skills={"cold calling", "b2b sales", "lead generation", "salesforce"},
        min_years_experience=1.0,
        preferred_years_experience=3.0,
        required_industries=set(),
        preferred_industries={"technology", "software", "fintech", "saas"},
    ),
    "UX Designer": RoleRequirements(
        canonical_role="UX Designer",
        required_skills={"ux design", "figma", "user research", "prototyping"},
        preferred_skills={"ui design", "interaction design", "design systems", "user testing"},
        min_years_experience=1.0,
        preferred_years_experience=3.0,
        required_industries=set(),
        preferred_industries={"technology", "software", "fintech", "ecommerce"},
    ),
}


class ProfileFitScorer:
    """
    Scores how well a user's profile matches a target role.

    Scoring factors:
    - Skills match (required skills have higher weight)
    - Experience level alignment
    - Industry relevance
    - Location preference
    """

    def __init__(self):
        self._cache: Dict[str, FitScore] = {}

    def score(
        self,
        profile: RicoProfile,
        target_role: str,
        location: Optional[str] = None,
    ) -> FitScore:
        """
        Score profile fit for a target role.

        Args:
            profile: User profile
            target_role: Canonical role title
            location: Target location (optional)

        Returns:
            FitScore with detailed breakdown
        """
        try:
            if not profile or not target_role:
                return self._default_fit_score(target_role or "Unknown", profile)

            cache_key = f"{profile.user_id}:{target_role}:{location}"
            if cache_key in self._cache:
                return self._cache[cache_key]

            # Get role requirements
            requirements = _ROLE_REQUIREMENTS.get(target_role)
            if not requirements:
                # Default requirements for unknown roles
                requirements = RoleRequirements(canonical_role=target_role)

            # Score each factor
            skills_score, missing_required, matched_required, matched_preferred = self._score_skills(
                profile, requirements
            )
            experience_score = self._score_experience(profile, requirements)
            industry_score = self._score_industry(profile, requirements)
            location_score = self._score_location(profile, location)

            # Weighted overall score
            overall_score = (
                skills_score * 0.5 +
                experience_score * 0.2 +
                industry_score * 0.2 +
                location_score * 0.1
            )

            fit_score = FitScore(
                overall_score=overall_score,
                skills_score=skills_score,
                experience_score=experience_score,
                industry_score=industry_score,
                location_score=location_score,
                missing_required_skills=missing_required,
                matched_required_skills=matched_required,
                matched_preferred_skills=matched_preferred,
                details={
                    "target_role": target_role,
                    "profile_user_id": profile.user_id,
                    "location": location,
                },
            )

            self._cache[cache_key] = fit_score
            return fit_score
        except Exception as e:
            logger.warning(f"Profile fit scoring failed for {target_role}: {e}")
            return self._default_fit_score(target_role or "Unknown", profile)

    def _score_skills(
        self,
        profile: RicoProfile,
        requirements: RoleRequirements,
    ) -> tuple[float, List[str], List[str], List[str]]:
        """Score skills match."""
        try:
            user_skills = set(skill.lower() for skill in (profile.skills or []))
            required_skills = set(skill.lower() for skill in requirements.required_skills)
            preferred_skills = set(skill.lower() for skill in requirements.preferred_skills)

            # Match required skills
            matched_required = [skill for skill in requirements.required_skills if skill.lower() in user_skills]
            missing_required = [skill for skill in requirements.required_skills if skill.lower() not in user_skills]

            # Match preferred skills
            matched_preferred = [skill for skill in requirements.preferred_skills if skill.lower() in user_skills]

            # Calculate score
            if not required_skills:
                # No required skills defined, score based on preferred
                if not preferred_skills:
                    skills_score = 0.5  # Neutral
                else:
                    skills_score = len(matched_preferred) / len(preferred_skills)
            else:
                # Required skills have 70% weight, preferred 30%
                required_score = len(matched_required) / len(required_skills)
                preferred_score = len(matched_preferred) / len(preferred_skills) if preferred_skills else 0.0
                skills_score = required_score * 0.7 + preferred_score * 0.3

            return skills_score, missing_required, matched_required, matched_preferred
        except Exception as e:
            logger.warning(f"Skills scoring failed: {e}")
            return 0.5, [], [], []

    def _score_experience(
        self,
        profile: RicoProfile,
        requirements: RoleRequirements,
    ) -> float:
        """Score experience level alignment."""
        try:
            user_years = profile.years_experience or 0

            if requirements.min_years_experience is None:
                return 0.5  # Neutral

            if user_years < requirements.min_years_experience:
                # Below minimum - penalize
                gap = requirements.min_years_experience - user_years
                score = max(0.0, 1.0 - gap / 2.0)  # 0.5 penalty per year below
            elif user_years > (requirements.preferred_years_experience or requirements.min_years_experience):
                # Above preferred - slight penalty for overqualification
                score = 0.9
            else:
                # Within range - perfect
                score = 1.0

            return score
        except Exception as e:
            logger.warning(f"Experience scoring failed: {e}")
            return 0.5

    def _score_industry(
        self,
        profile: RicoProfile,
        requirements: RoleRequirements,
    ) -> float:
        """Score industry relevance."""
        try:
            user_industries = set(ind.lower() for ind in (profile.industries or []))
            required_industries = set(ind.lower() for ind in requirements.required_industries)
            preferred_industries = set(ind.lower() for ind in requirements.preferred_industries)

            if not required_industries and not preferred_industries:
                return 0.5  # Neutral

            # Check required industries
            if required_industries:
                match = any(ind in user_industries for ind in required_industries)
                return 1.0 if match else 0.0

            # Check preferred industries
            if preferred_industries:
                matches = sum(1 for ind in preferred_industries if ind in user_industries)
                return matches / len(preferred_industries)

            return 0.5
        except Exception as e:
            logger.warning(f"Industry scoring failed: {e}")
            return 0.5

    def _score_location(
        self,
        profile: RicoProfile,
        location: Optional[str],
    ) -> float:
        """Score location preference."""
        try:
            if not location:
                return 0.5  # Neutral

            user_locations = set(loc.lower() for loc in (profile.preferred_cities or []))
            location_lower = location.lower()

            if location_lower in user_locations:
                return 1.0
            elif "remote" in location_lower and "remote" in user_locations:
                return 1.0
            else:
                return 0.0
        except Exception as e:
            logger.warning(f"Location scoring failed: {e}")
            return 0.5

    def _default_fit_score(self, target_role: str, profile: Optional[RicoProfile] = None) -> FitScore:
        """Return a neutral default fit score when scoring fails."""
        user_id = profile.user_id if profile else "unknown"
        return FitScore(
            overall_score=0.5,
            skills_score=0.5,
            experience_score=0.5,
            industry_score=0.5,
            location_score=0.5,
            missing_required_skills=[],
            matched_required_skills=[],
            matched_preferred_skills=[],
            details={
                "target_role": target_role,
                "profile_user_id": user_id,
                "fallback": True,
            },
        )


# Module-level singleton
_profile_fit_scorer = ProfileFitScorer()


def score_profile_fit(
    profile: RicoProfile,
    target_role: str,
    location: Optional[str] = None,
) -> FitScore:
    """
    Convenience function to score profile fit.

    Uses the singleton ProfileFitScorer instance.
    """
    return _profile_fit_scorer.score(profile, target_role, location)
