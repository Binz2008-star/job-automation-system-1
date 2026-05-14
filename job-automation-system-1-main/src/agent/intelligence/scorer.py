"""src/agent/intelligence/scorer.py

Profile-fit scoring for Rico Agent OS.

Scores how well a user's profile matches a target role:
- Skills match (required vs optional) with fuzzy matching
- Experience level alignment
- Industry relevance
- Location preference
- Overall fit score (0.0-1.0)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz, process

from src.rico_agent import RicoProfile

logger = logging.getLogger(__name__)

# Fuzzy matching thresholds
REQUIRED_SKILL_THRESHOLD = 75  # Core skills need high confidence
PREFERRED_SKILL_THRESHOLD = 60  # Preferred skills can be looser
INDUSTRY_MATCH_THRESHOLD = 80   # Industry names should match closely
MIN_FUZZY_LENGTH = 3  # Minimum length for fuzzy matching (shorter strings require exact match)

# Scoring weights (UAE-market optimized)
SCORING_WEIGHTS = {
    "skills": 0.5,      # Skills matter most
    "experience": 0.2,   # Experience valued but flexible
    "industry": 0.2,     # Industry fit important
    "location": 0.1,     # Location preference (lower weight)
}

# Cache management
MAX_CACHE_SIZE = 1000


@dataclass
class RoleRequirements:
    """Requirements for a target role."""
    canonical_role: str
    required_skills: set[str] = field(default_factory=set)
    preferred_skills: set[str] = field(default_factory=set)
    min_years_experience: float | None = None
    preferred_years_experience: float | None = None
    required_industries: set[str] = field(default_factory=set)
    preferred_industries: set[str] = field(default_factory=set)


@dataclass
class FitScore:
    """Result of profile-fit scoring."""
    overall_score: float  # 0.0-1.0
    skills_score: float  # 0.0-1.0
    experience_score: float  # 0.0-1.0
    industry_score: float  # 0.0-1.0
    location_score: float  # 0.0-1.0
    missing_required_skills: list[str] = field(default_factory=list)
    matched_required_skills: list[str] = field(default_factory=list)
    matched_preferred_skills: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


# Predefined role requirements (UAE-market focused)
_ROLE_REQUIREMENTS: dict[str, RoleRequirements] = {
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
    "HSE Manager": RoleRequirements(
        canonical_role="HSE Manager",
        required_skills={"osha", "iso 45001", "risk assessment", "safety audit"},
        preferred_skills={"nema", "environmental management", "incident investigation", "hazop"},
        min_years_experience=5.0,
        preferred_years_experience=8.0,
        required_industries={"construction", "oil & gas", "manufacturing"},
        preferred_industries={"energy", "infrastructure", "logistics"},
    ),
    "Operations Manager": RoleRequirements(
        canonical_role="Operations Manager",
        required_skills={"supply chain", "erp", "team leadership", "process improvement"},
        preferred_skills={"sap", "oracle", "lean six sigma", "budgeting"},
        min_years_experience=3.0,
        preferred_years_experience=7.0,
        required_industries=set(),
        preferred_industries={"logistics", "manufacturing", "retail", "ecommerce"},
    ),
    "Business Development Manager": RoleRequirements(
        canonical_role="Business Development Manager",
        required_skills={"sales", "negotiation", "client acquisition", "crm"},
        preferred_skills={"b2b sales", "market analysis", "partnerships", "salesforce"},
        min_years_experience=3.0,
        preferred_years_experience=6.0,
        required_industries=set(),
        preferred_industries={"fintech", "technology", "saas", "consulting"},
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

    Uses fuzzy matching for skills and industries to handle:
    - Typos ("pyhton" → "python")
    - Abbreviations ("ML" → "machine learning")
    - Variations ("AWS cloud" → "aws")

    Scoring factors for UAE market:
    - Skills match (50% weight)
    - Experience alignment (20% weight, UAE prefers 3-7 years)
    - Industry relevance (20% weight)
    - Location preference (10% weight, Dubai/Abu Dhabi premium)
    """

    def __init__(self):
        self._cache: dict[str, FitScore] = {}

    def score(
        self,
        profile: RicoProfile,
        target_role: str,
        location: str | None = None,
    ) -> FitScore:
        """
        Score profile fit for a target role.

        Raises:
            ValueError: If profile or target_role is invalid
        """
        if not profile or not profile.user_id:
            raise ValueError("Valid profile with user_id required")

        if not target_role:
            raise ValueError("Target role required")

        cache_key = f"{profile.user_id}:{target_role}:{location}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Get or create requirements
        requirements = _ROLE_REQUIREMENTS.get(target_role)
        if not requirements:
            logger.info(f"No predefined requirements for '{target_role}', using defaults")
            requirements = RoleRequirements(canonical_role=target_role)

        # Score each factor
        skills_score, missing_required, matched_required, matched_preferred = self._score_skills(
            profile, requirements
        )
        experience_score = self._score_experience(profile, requirements)
        industry_score = self._score_industry(profile, requirements)
        location_score = self._score_location(profile, location)

        # Weighted overall score (UAE-optimized)
        overall_score = (
            skills_score * SCORING_WEIGHTS["skills"] +
            experience_score * SCORING_WEIGHTS["experience"] +
            industry_score * SCORING_WEIGHTS["industry"] +
            location_score * SCORING_WEIGHTS["location"]
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

        # Cache eviction policy
        if len(self._cache) >= MAX_CACHE_SIZE:
            self._cache.clear()
            logger.info("Scorer cache cleared (reached max size)")

        self._cache[cache_key] = fit_score
        return fit_score

    def _score_skills(
        self,
        profile: RicoProfile,
        requirements: RoleRequirements,
    ) -> tuple[float, list[str], list[str], list[str]]:
        """Score skills match using fuzzy matching."""
        user_skills = [skill.lower().strip() for skill in (profile.skills or [])]

        if not user_skills:
            return 0.0, list(requirements.required_skills), [], []

        # Fuzzy match required skills
        matched_required = []
        missing_required = []

        for required_skill in requirements.required_skills:
            skill_lower = required_skill.lower()
            # Try exact match first (fast path)
            if skill_lower in user_skills:
                matched_required.append(required_skill)
                continue

            # Fuzzy match with threshold (only if string is long enough)
            if len(skill_lower) >= MIN_FUZZY_LENGTH:
                result = process.extractOne(
                    skill_lower,
                    user_skills,
                    scorer=fuzz.ratio,
                    score_cutoff=REQUIRED_SKILL_THRESHOLD
                )

                if result:
                    matched_required.append(required_skill)
                else:
                    missing_required.append(required_skill)
            else:
                # Short strings require exact match
                missing_required.append(required_skill)

        # Fuzzy match preferred skills
        matched_preferred = []

        for preferred_skill in requirements.preferred_skills:
            skill_lower = preferred_skill.lower()

            # Try exact match
            if skill_lower in user_skills:
                matched_preferred.append(preferred_skill)
                continue

            # Fuzzy match with lower threshold (only if string is long enough)
            if len(skill_lower) >= MIN_FUZZY_LENGTH:
                result = process.extractOne(
                    skill_lower,
                    user_skills,
                    scorer=fuzz.partial_ratio,
                    score_cutoff=PREFERRED_SKILL_THRESHOLD
                )

                if result:
                    matched_preferred.append(preferred_skill)

        # Calculate score
        if not requirements.required_skills:
            # No required skills defined, score based on preferred
            if not requirements.preferred_skills:
                skills_score = 0.5  # Neutral
            else:
                skills_score = len(matched_preferred) / len(requirements.preferred_skills)
        else:
            # Required skills have 70% weight, preferred 30%
            required_score = len(matched_required) / len(requirements.required_skills)
            preferred_score = (
                len(matched_preferred) / len(requirements.preferred_skills)
                if requirements.preferred_skills
                else 0.0
            )
            skills_score = required_score * 0.7 + preferred_score * 0.3

        return skills_score, missing_required, matched_required, matched_preferred

    def _score_experience(
        self,
        profile: RicoProfile,
        requirements: RoleRequirements,
    ) -> float:
        """
        Score experience level alignment for UAE market.

        UAE employers typically value:
        - Junior: 0-2 years
        - Mid-level: 3-5 years
        - Senior: 6-9 years
        - Executive: 10+ years

        Overqualification is penalized less (UAE welcomes senior talent pivoting).
        """
        user_years = profile.years_experience or 0.0

        # No requirements - neutral score
        if requirements.min_years_experience is None:
            return 0.5

        # Severe underqualification
        if user_years < requirements.min_years_experience:
            gap = requirements.min_years_experience - user_years
            # Gentler penalty: 0.2 per year below (vs 0.5 before)
            score = max(0.0, 1.0 - (gap * 0.2))
            return score

        # Ideal range (min to preferred*1.2)
        max_ideal = (requirements.preferred_years_experience or requirements.min_years_experience) * 1.2
        if user_years <= max_ideal:
            return 1.0

        # Overqualified but still valuable (UAE welcomes senior talent)
        overqualification_ratio = min(1.0, (user_years - max_ideal) / 10.0)
        # Floor at 0.85 instead of 0.9 to be slightly more forgiving for very senior
        return max(0.85, 1.0 - (overqualification_ratio * 0.15))

    def _score_industry(
        self,
        profile: RicoProfile,
        requirements: RoleRequirements,
    ) -> float:
        """Score industry relevance using fuzzy matching."""
        user_industries = [ind.lower().strip() for ind in (profile.industries or [])]

        if not user_industries:
            return 0.0

        # Required industries (must match at least one)
        if requirements.required_industries:
            for required_ind in requirements.required_industries:
                ind_lower = required_ind.lower()

                # Exact match
                if ind_lower in user_industries:
                    return 1.0

                # Fuzzy match for industry names (only if long enough)
                if len(ind_lower) >= MIN_FUZZY_LENGTH:
                    result = process.extractOne(
                        ind_lower,
                        user_industries,
                        scorer=fuzz.ratio,
                        score_cutoff=INDUSTRY_MATCH_THRESHOLD
                    )
                    if result:
                        return 1.0

            return 0.0  # No required industry matched

        # Preferred industries (score based on matches)
        if requirements.preferred_industries:
            matches = 0
            for preferred_ind in requirements.preferred_industries:
                ind_lower = preferred_ind.lower()

                if ind_lower in user_industries:
                    matches += 1
                    continue

                if len(ind_lower) >= MIN_FUZZY_LENGTH:
                    result = process.extractOne(
                        ind_lower,
                        user_industries,
                        scorer=fuzz.ratio,
                        score_cutoff=INDUSTRY_MATCH_THRESHOLD
                    )
                    if result:
                        matches += 1

            return matches / len(requirements.preferred_industries)

        # No industry preferences
        return 0.5

    def _score_location(
        self,
        profile: RicoProfile,
        location: str | None,
    ) -> float:
        """Score location preference (UAE-focused)."""
        if not location:
            return 0.5  # No preference stated

        user_locations = [loc.lower().strip() for loc in (profile.preferred_cities or [])]
        location_lower = location.lower()

        # Check for remote work
        if "remote" in location_lower:
            return 1.0 if any("remote" in loc for loc in user_locations) else 0.3

        # Exact match
        if location_lower in user_locations:
            return 1.0

        # UAE city matching (Dubai ↔ DXB, Abu Dhabi ↔ AUH)
        uae_city_aliases = {
            "dubai": ["dubai", "dxb", "dub"],
            "abu dhabi": ["abu dhabi", "auh", "abudhabi"],
            "sharjah": ["sharjah", "shj"],
        }

        for city, aliases in uae_city_aliases.items():
            if location_lower in aliases and any(alias in user_locations for alias in aliases):
                return 1.0

        # Partial match (e.g., "Dubai Marina" vs "Dubai")
        for user_loc in user_locations:
            if user_loc in location_lower or location_lower in user_loc:
                return 0.8

        return 0.0


# Lazy singleton - module-level instance without global state pollution
_scorer: ProfileFitScorer | None = None
_scorer_lock = threading.Lock()


def score_profile_fit(
    profile: RicoProfile,
    target_role: str,
    location: str | None = None,
) -> FitScore:
    """
    Score profile fit for a target role.

    This is the main entry point. Uses lazy initialization of the scorer
    to avoid unnecessary object creation while maintaining a clean API.

    Example:
        >>> score = score_profile_fit(profile, "Software Engineer", "Dubai")
        >>> print(f"Match: {score.overall_score:.2f}")

    Args:
        profile: User profile with skills, experience, etc.
        target_role: Target role title (e.g., "Software Engineer")
        location: Preferred location (optional, e.g., "Dubai")

    Returns:
        FitScore with detailed breakdown

    Raises:
        ValueError: If profile or target_role is invalid
    """
    global _scorer
    if _scorer is None:
        with _scorer_lock:
            if _scorer is None:
                _scorer = ProfileFitScorer()
    return _scorer.score(profile, target_role, location)


def clear_scorer_cache() -> None:
    """Clear the scorer's cache (useful for testing)."""
    if _scorer:
        _scorer._cache.clear()
