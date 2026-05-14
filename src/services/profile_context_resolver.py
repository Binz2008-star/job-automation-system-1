"""Profile context resolver — unified canonical view of a Rico user profile.

Problem: profile data arrives from CV parser, Jotform webhooks, chat
updates, and DB reads. Each source uses slightly different shapes
(dict vs dataclass, missing keys, divergent list formats).

Solution: this module normalises any source into a single typed
`ProfileContext` that the chat layer (and future agent layer) can
consume without defensive `getattr` / `.get()` checks.

Design goals
--------------
* Single source of truth for profile field names and defaults.
* No external I/O — pure in-memory transformation.
* Immutable-ish (frozen dataclass) so it is safe to pass around.
* Computes derived state (has_cv, completion_score, missing_fields)
  so the chat layer doesn't duplicate that logic.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

from src.rico_agent import RicoProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Essential field names used by the chat layer
# ---------------------------------------------------------------------------

_ESSENTIAL_FIELDS: Set[str] = {
    "name",
    "email",
    "phone",
    "current_location",
    "target_roles",
    "years_experience",
    "salary_expectation_aed",
    "minimum_salary_aed",
    "preferred_cities",
    "visa_status",
    "notice_period",
    "skills",
    "industries",
    "tools",
    "languages",
    "current_role",
    "current_company",
    "linkedin_url",
    "portfolio_url",
    "deal_breakers",
    "green_flags",
    "red_flags",
    "cv_filename",
    "cv_status",
    "profile_creation_mode",
    "manual_profile_wizard_disabled",
}

# Fields that contribute to "profile completeness"
_COMPLETENESS_FIELDS: List[str] = [
    "skills",
    "years_experience",
    "target_roles",
    "preferred_cities",
    "salary_expectation_aed",
    "current_role",
    "industries",
]


# ---------------------------------------------------------------------------
# ProfileContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProfileContext:
    """Canonical, normalised view of a Rico user profile.

    All list fields are guaranteed to be ``list`` (never ``None``).
    All scalar fields may be ``None``.
    """

    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    current_location: Optional[str] = None
    target_roles: List[str] = field(default_factory=list)
    years_experience: Optional[float] = None
    salary_expectation_aed: Optional[int] = None
    minimum_salary_aed: Optional[int] = None
    preferred_cities: List[str] = field(default_factory=list)
    visa_status: Optional[str] = None
    notice_period: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    industries: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    deal_breakers: List[str] = field(default_factory=list)
    green_flags: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    cv_filename: Optional[str] = None
    cv_status: Optional[str] = None
    profile_creation_mode: Optional[str] = None
    manual_profile_wizard_disabled: bool = False

    # --- derived properties ------------------------------------------------

    @property
    def has_cv(self) -> bool:
        """True when the profile carries CV-derived data."""
        return bool(
            self.cv_filename
            or self.cv_status == "parsed"
            or self.skills
            or self.years_experience is not None
        )

    @property
    def completion_score(self) -> float:
        """0.0–1.0 ratio of filled essential fields."""
        total = len(_COMPLETENESS_FIELDS)
        if total == 0:
            return 0.0
        filled = 0
        for key in _COMPLETENESS_FIELDS:
            val = getattr(self, key)
            if val is not None and val != [] and val != "":
                filled += 1
        return filled / total

    @property
    def missing_fields(self) -> List[str]:
        """Names of essential fields that are still empty."""
        missing: List[str] = []
        for key in _COMPLETENESS_FIELDS:
            val = getattr(self, key)
            if val is None or val == [] or val == "":
                missing.append(key)
        return missing

    @property
    def is_onboarding_complete(self) -> bool:
        """Heuristic: enough fields filled + CV parsed → onboarding done."""
        return self.has_cv and self.completion_score >= 0.5

    # --- helpers for the chat layer ----------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style accessor for backwards compatibility."""
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain dict (useful for JSON responses)."""
        return asdict(self)

    def summary_text(self, max_chars: int = 500) -> str:
        """One-line human-readable summary for OpenAI prompts."""
        parts: List[str] = []
        if self.current_role:
            parts.append(f"Current: {self.current_role}")
        if self.target_roles:
            parts.append(f"Target: {', '.join(self.target_roles[:3])}")
        if self.years_experience is not None:
            parts.append(f"~{self.years_experience} yrs")
        if self.skills:
            parts.append(f"Skills: {', '.join(self.skills[:8])}")
        if self.preferred_cities:
            parts.append(f"Cities: {', '.join(self.preferred_cities[:3])}")
        text = " | ".join(parts)
        return text[:max_chars]


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

def _as_list(value: Any) -> List[Any]:
    """Normalise a value to a flat list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        # Comma-separated strings are common in web form payloads
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def _as_float(value: Any) -> Optional[float]:
    """Coerce a value to float, or None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _as_int(value: Any) -> Optional[int]:
    """Coerce a value to int, or None."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _as_str(value: Any) -> Optional[str]:
    """Coerce a value to a clean string, or None."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def resolve_profile_context(
    user_id: str,
    raw: Any,
) -> ProfileContext:
    """Normalise *any* profile shape into a ``ProfileContext``.

    Supports:
    * ``RicoProfile`` dataclass instances
    * ``dict`` (from Jotform, JSON store, DB rows)
    * Any object with attribute access (from ORM, mocked profiles)
    * ``None`` (returns empty context for the user)
    """
    if raw is None:
        return ProfileContext(user_id=user_id)

    # Helper that reads from dict or object transparently
    def _read(key: str) -> Any:
        if isinstance(raw, dict):
            # Try exact key, then common aliases
            val = raw.get(key)
            if val is None:
                # Common aliases
                aliases = {
                    "current_location": {"location", "city", "current_city"},
                    "preferred_cities": {"cities", "preferred_locations"},
                    "target_roles": {"target_role", "desired_roles", "job_titles"},
                    "years_experience": {"experience_years", "years_of_experience"},
                    "salary_expectation_aed": {"salary_max", "expected_salary"},
                    "minimum_salary_aed": {"salary_min"},
                    "current_role": {"current_job_title", "job_title"},
                    "current_company": {"company", "employer"},
                    "deal_breakers": {"hard_reject_keywords", "reject_keywords"},
                }
                for alias in aliases.get(key, set()):
                    val = raw.get(alias)
                    if val is not None:
                        break
            return val
        return getattr(raw, key, None)

    def _read_bool(key: str, default: bool = False) -> bool:
        val = _read(key)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).lower() in {"true", "1", "yes", "on"}

    return ProfileContext(
        user_id=user_id,
        name=_as_str(_read("name")),
        email=_as_str(_read("email")),
        phone=_as_str(_read("phone")),
        telegram_username=_as_str(_read("telegram_username")),
        current_location=_as_str(_read("current_location")),
        target_roles=_as_list(_read("target_roles")),
        years_experience=_as_float(_read("years_experience")),
        salary_expectation_aed=_as_int(_read("salary_expectation_aed")),
        minimum_salary_aed=_as_int(_read("minimum_salary_aed")),
        preferred_cities=_as_list(_read("preferred_cities")),
        visa_status=_as_str(_read("visa_status")),
        notice_period=_as_str(_read("notice_period")),
        skills=_as_list(_read("skills")),
        industries=_as_list(_read("industries")),
        tools=_as_list(_read("tools")),
        languages=_as_list(_read("languages")),
        current_role=_as_str(_read("current_role")),
        current_company=_as_str(_read("current_company")),
        linkedin_url=_as_str(_read("linkedin_url")),
        portfolio_url=_as_str(_read("portfolio_url")),
        deal_breakers=_as_list(_read("deal_breakers")),
        green_flags=_as_list(_read("green_flags")),
        red_flags=_as_list(_read("red_flags")),
        cv_filename=_as_str(_read("cv_filename")),
        cv_status=_as_str(_read("cv_status")),
        profile_creation_mode=_as_str(_read("profile_creation_mode")),
        manual_profile_wizard_disabled=_read_bool("manual_profile_wizard_disabled"),
    )
