"""src/agent/intelligence

Role intelligence layer for Rico Agent OS.

Provides:
- Role normalization (sales man → Sales Representative)
- CV-fit scoring (profile vs target role)
- Adjacent role recommendations from CV skills
"""
from __future__ import annotations

from src.agent.intelligence.normalizer import RoleNormalizer, normalize_role
from src.agent.intelligence.scorer import ProfileFitScorer, score_profile_fit
from src.agent.intelligence.recommender import AdjacentRoleRecommender, recommend_adjacent_roles

__all__ = [
    "RoleNormalizer",
    "normalize_role",
    "ProfileFitScorer",
    "score_profile_fit",
    "AdjacentRoleRecommender",
    "recommend_adjacent_roles",
]
