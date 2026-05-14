"""src/agent/intelligence/recommender.py

Adjacent role recommendations from CV skills for Rico Agent OS.

Recommends roles similar to user's target role based on their skills:
- If user is a "Software Engineer" with Python skills, recommend "Data Scientist"
- If user is a "Sales Rep" with CRM skills, recommend "Account Executive"
- Based on skill overlap and role similarity
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from src.rico_agent import RicoProfile
from src.agent.intelligence.normalizer import normalize_role
from src.agent.intelligence.scorer import _ROLE_REQUIREMENTS, RoleRequirements

logger = logging.getLogger(__name__)


@dataclass
class RoleRecommendation:
    """A recommended adjacent role."""
    canonical_role: str
    similarity_score: float  # 0.0-1.0
    reason: str  # Why this role is recommended
    shared_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    fit_score: Optional[float] = None  # Profile fit for this role


# Role similarity graph (based on skill overlap)
_ROLE_SIMILARITY: Dict[str, List[Tuple[str, float]]] = {
    "Software Engineer": [
        ("Data Scientist", 0.7),
        ("Machine Learning Engineer", 0.8),
        ("DevOps Engineer", 0.75),
        ("Full Stack Engineer", 0.9),
        ("Backend Engineer", 0.85),
        ("Frontend Engineer", 0.7),
    ],
    "Product Manager": [
        ("Program Manager", 0.85),
        ("Project Manager", 0.75),
        ("Product Owner", 0.9),
        ("Business Analyst", 0.7),
    ],
    "Data Scientist": [
        ("Machine Learning Engineer", 0.85),
        ("Data Analyst", 0.8),
        ("Data Engineer", 0.75),
        ("Research Scientist", 0.7),
    ],
    "Sales Representative": [
        ("Account Executive", 0.9),
        ("Business Development Representative", 0.85),
        ("Sales Manager", 0.7),
        ("Customer Success Manager", 0.65),
    ],
    "UX Designer": [
        ("Product Designer", 0.85),
        ("UI Designer", 0.8),
        ("User Researcher", 0.75),
        ("Service Designer", 0.7),
    ],
}


class AdjacentRoleRecommender:
    """
    Recommends adjacent roles based on user's skills and current target role.

    Uses:
    - Predefined role similarity graph
    - Skill overlap analysis
    - Profile fit scoring
    """

    def __init__(self):
        self._cache: Dict[str, List[RoleRecommendation]] = {}

    def recommend(
        self,
        profile: RicoProfile,
        target_role: str,
        limit: int = 5,
        location: Optional[str] = None,
    ) -> List[RoleRecommendation]:
        """
        Recommend adjacent roles for a user.

        Args:
            profile: User profile
            target_role: Current target role
            limit: Max number of recommendations
            location: Target location (optional)

        Returns:
            List of RoleRecommendation sorted by similarity
        """
        try:
            if not profile or not target_role:
                return []

            cache_key = f"{profile.user_id}:{target_role}:{location}:{limit}"
            if cache_key in self._cache:
                return self._cache[cache_key]

            # Normalize target role
            normalized_target = normalize_role(target_role)

            # Get similar roles from graph
            similar_roles = _ROLE_SIMILARITY.get(normalized_target, [])

            if not similar_roles:
                logger.info(f"No similar roles found for {normalized_target}")
                return []

            # Score each similar role
            recommendations: List[RoleRecommendation] = []
            for similar_role, base_similarity in similar_roles:
                try:
                    # Calculate skill overlap
                    shared_skills, missing_skills = self._analyze_skill_overlap(profile, similar_role)

                    # Calculate similarity score (base similarity + skill overlap)
                    skill_overlap_score = len(shared_skills) / max(1, len(profile.skills or []))
                    similarity_score = base_similarity * 0.6 + skill_overlap_score * 0.4

                    # Generate reason
                    reason = self._generate_reason(normalized_target, similar_role, shared_skills)

                    # Score profile fit for this role
                    from src.agent.intelligence.scorer import score_profile_fit
                    fit_score = score_profile_fit(profile, similar_role, location)

                    recommendations.append(
                        RoleRecommendation(
                            canonical_role=similar_role,
                            similarity_score=similarity_score,
                            reason=reason,
                            shared_skills=shared_skills,
                            missing_skills=missing_skills,
                            fit_score=fit_score.overall_score,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to score recommendation for {similar_role}: {e}")
                    continue

            # Sort by similarity score
            recommendations.sort(key=lambda r: r.similarity_score, reverse=True)

            # Limit results
            recommendations = recommendations[:limit]

            self._cache[cache_key] = recommendations
            return recommendations
        except Exception as e:
            logger.warning(f"Role recommendation failed for {target_role}: {e}")
            return []

    def _analyze_skill_overlap(
        self,
        profile: RicoProfile,
        role: str,
    ) -> tuple[List[str], List[str]]:
        """Analyze skill overlap between profile and role."""
        try:
            user_skills = set(skill.lower() for skill in (profile.skills or []))

            requirements = _ROLE_REQUIREMENTS.get(role)
            if not requirements:
                return [], []

            role_skills = requirements.required_skills | requirements.preferred_skills
            role_skills_lower = set(skill.lower() for skill in role_skills)

            shared = [skill for skill in role_skills if skill.lower() in user_skills]
            missing = [skill for skill in role_skills if skill.lower() not in user_skills]

            return shared, missing
        except Exception as e:
            logger.warning(f"Skill overlap analysis failed for {role}: {e}")
            return [], []

    def _generate_reason(
        self,
        current_role: str,
        recommended_role: str,
        shared_skills: List[str],
    ) -> str:
        """Generate a reason for the recommendation."""
        try:
            if not shared_skills:
                return f"{recommended_role} is a common career progression from {current_role}."

            skill_list = ", ".join(shared_skills[:3])
            return (
                f"Your {skill_list} skills from {current_role} "
                f"transfer well to {recommended_role}."
            )
        except Exception as e:
            logger.warning(f"Reason generation failed: {e}")
            return f"{recommended_role} is a similar role to {current_role}."


# Module-level singleton
_adjacent_role_recommender = AdjacentRoleRecommender()


def recommend_adjacent_roles(
    profile: RicoProfile,
    target_role: str,
    limit: int = 5,
    location: Optional[str] = None,
) -> List[RoleRecommendation]:
    """
    Convenience function to recommend adjacent roles.

    Uses the singleton AdjacentRoleRecommender instance.
    """
    return _adjacent_role_recommender.recommend(profile, target_role, limit, location)
