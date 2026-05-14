"""Tool registry for Rico OpenAI agent.

Maps Rico's tool-calling layer to the existing job automation modules.
All functions are defensive and additive.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.rico_agent import RicoProfile
from src.rico_memory import RicoMemoryStore
from src.rico_openai_runtime import call_openai_minimal
from src.rico_repo_adapter import RicoSystem, run_rico_for_default_profile
from src.repositories.profile_repo import get_profile

logger = logging.getLogger(__name__)


def _profile_to_rico_profile(user_id: str, profile: Any) -> RicoProfile:
    """Convert a dict/object profile from the repo into a RicoProfile."""
    if profile is None:
        return RicoProfile(user_id=user_id)

    def _get(key: str, default: Any = None) -> Any:
        if isinstance(profile, dict):
            return profile.get(key, default)
        return getattr(profile, key, default)

    # Normalize list fields
    def _as_list(value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    return RicoProfile(
        user_id=user_id,
        name=_get("name"),
        email=_get("email"),
        phone=_get("phone"),
        current_location=_get("current_location") or _get("location"),
        target_roles=_as_list(_get("target_roles")),
        years_experience=_get("years_experience"),
        salary_expectation_aed=_get("salary_expectation_aed"),
        minimum_salary_aed=_get("minimum_salary_aed"),
        preferred_cities=_as_list(_get("preferred_cities") or _get("cities")),
        skills=_as_list(_get("skills")),
        industries=_as_list(_get("industries")),
        current_role=_get("current_role"),
        current_company=_get("current_company"),
        deal_breakers=_as_list(_get("deal_breakers")),
        cv_filename=_get("cv_filename"),
        cv_status=_get("cv_status"),
    )


def search_jobs(
    query: str,
    city: str | None = None,
    limit: int = 10,
    user_id: str = "default",
    **_: Any,
) -> Dict[str, Any]:
    """Run Rico's recommendation workflow scoped to the requesting user.

    Authenticated users without a profile get an explicit empty result.
    Only the literal "default" user falls back to the global demo profile.
    """
    profile_obj = get_profile(user_id)
    if profile_obj:
        try:
            profile = _profile_to_rico_profile(user_id, profile_obj)
            result = RicoSystem().run_for_profile(profile, limit=limit)
        except Exception as exc:
            logger.warning("user_scoped_search_failed: %s", exc)
            if user_id == "default":
                result = run_rico_for_default_profile()
            else:
                return {
                    "query": query,
                    "city": city,
                    "count": 0,
                    "matches": [],
                    "status": "search_error",
                }
    elif user_id == "default":
        result = run_rico_for_default_profile()
    else:
        return {
            "query": query,
            "city": city,
            "count": 0,
            "matches": [],
            "status": "profile_required",
            "message": "A user profile is required before searching jobs. Upload your CV or complete onboarding first.",
        }

    matches = result.get("matches", [])[:limit]
    if city:
        city_lower = city.lower()
        matches = [m for m in matches if city_lower in str(m.get("location", "")).lower()]
    return {
        "query": query,
        "city": city,
        "count": len(matches),
        "matches": matches,
    }


def update_preferences(user_id: str = "default", preferences: Dict[str, Any] | None = None, **_: Any) -> Dict[str, Any]:
    memory = RicoMemoryStore()
    profile = memory.upsert_profile_from_dict(user_id, preferences or {})
    return {
        "status": "updated",
        "user_id": user_id,
        "profile": profile.user_id,
    }


def write_cover_letter(
    job_id: str,
    job_title: str = "",
    company: str = "",
    tone: str = "professional",
    user_id: str = "default",
    **_: Any,
) -> Dict[str, Any]:
    """Generate a cover letter draft using the user's profile and job details."""
    profile_obj = get_profile(user_id)
    profile_ctx = ""
    if profile_obj:
        if isinstance(profile_obj, dict):
            skills = profile_obj.get("skills", [])
            years = profile_obj.get("years_experience")
            target_roles = profile_obj.get("target_roles", [])
            current_role = profile_obj.get("current_role", "")
        else:
            skills = getattr(profile_obj, "skills", []) or []
            years = getattr(profile_obj, "years_experience", None)
            target_roles = getattr(profile_obj, "target_roles", []) or []
            current_role = getattr(profile_obj, "current_role", "")

        parts = []
        if current_role:
            parts.append(f"Current role: {current_role}")
        if target_roles:
            parts.append(f"Target roles: {', '.join(str(r) for r in target_roles[:3])}")
        if skills:
            parts.append(f"Skills: {', '.join(str(s) for s in skills[:8])}")
        if years is not None:
            parts.append(f"Experience: {years} years")
        profile_ctx = "\n".join(parts)

    prompt = (
        f"Write a {tone} cover letter for the position of {job_title} at {company}.\n"
        f"Candidate profile:\n{profile_ctx}\n\n"
        "Keep it concise (3–4 paragraphs), specific to the role, and professional."
    )

    result = call_openai_minimal(user_message=prompt, profile_context=profile_ctx or None)
    return {
        "status": "draft_ready" if result.get("success") else "draft_failed",
        "job_id": job_id,
        "job_title": job_title,
        "company": company,
        "tone": tone,
        "cover_letter": result.get("text", ""),
        "ai_provider": result.get("provider"),
        "model": result.get("model"),
    }


def prepare_interview(
    job_id: str,
    job_title: str = "",
    company: str = "",
    user_id: str = "default",
    **_: Any,
) -> Dict[str, Any]:
    """Generate interview preparation content using the user's profile."""
    profile_obj = get_profile(user_id)
    profile_ctx = ""
    if profile_obj:
        if isinstance(profile_obj, dict):
            skills = profile_obj.get("skills", [])
            years = profile_obj.get("years_experience")
            target_roles = profile_obj.get("target_roles", [])
            current_role = profile_obj.get("current_role", "")
            certifications = profile_obj.get("certifications", [])
        else:
            skills = getattr(profile_obj, "skills", []) or []
            years = getattr(profile_obj, "years_experience", None)
            target_roles = getattr(profile_obj, "target_roles", []) or []
            current_role = getattr(profile_obj, "current_role", "")
            certifications = getattr(profile_obj, "certifications", []) or []

        parts = []
        if current_role:
            parts.append(f"Current role: {current_role}")
        if target_roles:
            parts.append(f"Target roles: {', '.join(str(r) for r in target_roles[:3])}")
        if skills:
            parts.append(f"Skills: {', '.join(str(s) for s in skills[:8])}")
        if certifications:
            parts.append(f"Certifications: {', '.join(str(c) for c in certifications[:5])}")
        if years is not None:
            parts.append(f"Experience: {years} years")
        profile_ctx = "\n".join(parts)

    prompt = (
        f"Prepare interview guidance for the position of {job_title} at {company}.\n"
        f"Candidate profile:\n{profile_ctx}\n\n"
        "Provide:\n"
        "1. 5 likely interview questions specific to this role and the candidate's background\n"
        "2. Suggested talking points that connect the candidate's experience to the role\n"
        "3. 3 smart questions the candidate should ask the interviewer\n"
        "4. One salary negotiation tip relevant to UAE market\n"
        "Be concise and actionable."
    )

    result = call_openai_minimal(user_message=prompt, profile_context=profile_ctx or None)
    return {
        "status": "prep_ready" if result.get("success") else "prep_failed",
        "job_id": job_id,
        "job_title": job_title,
        "company": company,
        "prep_content": result.get("text", ""),
        "ai_provider": result.get("provider"),
        "model": result.get("model"),
    }


def track_application(job_id: str, status: str, user_id: str = "default", **_: Any) -> Dict[str, Any]:
    memory = RicoMemoryStore()
    memory.record_learning_signal(user_id, job_id, f"application_{status}")
    return {
        "status": "tracked",
        "user_id": user_id,
        "job_id": job_id,
        "application_status": status,
    }


def get_rico_tools() -> Dict[str, Any]:
    return {
        "search_jobs": search_jobs,
        "update_preferences": update_preferences,
        "write_cover_letter": write_cover_letter,
        "prepare_interview": prepare_interview,
        "track_application": track_application,
    }
