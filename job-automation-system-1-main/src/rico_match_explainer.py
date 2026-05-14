"""Rule-based structured match explanations for Rico job recommendations.

V1 principle: deterministic, short, honest explanations.  This module does not
predict hiring probability; it explains whether a recommendation is worth the
user's attention based on profile fit and available facts.
"""
from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Literal

Confidence = Literal["high", "medium", "low"]

_CRITICAL_MISSING = (
    "salary range",
    "visa requirements",
    "experience level",
    "language requirements",
)

_SENIOR_TERMS = {"senior", "lead", "manager", "head", "director", "chief", "vp"}
_JUNIOR_TERMS = {"junior", "assistant", "trainee", "intern", "entry"}


def _to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    result: Dict[str, Any] = {}
    for key in dir(value):
        if key.startswith("_"):
            continue
        try:
            attr = getattr(value, key)
        except Exception:
            continue
        if not callable(attr):
            result[key] = attr
    return result


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        return [part.strip() for part in re.split(r"[,;|]", value) if part.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _text(*parts: Any) -> str:
    return " ".join(str(part or "") for part in parts).lower()


def _contains_any(haystack: str, needles: Iterable[str]) -> bool:
    haystack_l = haystack.lower()
    return any(needle.lower() in haystack_l for needle in needles if needle)


def _salary_number(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).lower().replace(",", "")
    numbers = [int(n) for n in re.findall(r"\d{4,6}", text)]
    if not numbers:
        # Handle compact ranges such as AED 25k.
        compact = [int(n) * 1000 for n in re.findall(r"\b(\d{2,3})\s*k\b", text)]
        numbers = compact
    return max(numbers) if numbers else None


def _has_salary(job: Dict[str, Any]) -> bool:
    return bool(job.get("salary") or job.get("salary_range") or job.get("compensation"))


def _salary_text(job: Dict[str, Any]) -> str:
    return str(job.get("salary") or job.get("salary_range") or job.get("compensation") or "")


def _job_text(job: Dict[str, Any]) -> str:
    return _text(
        job.get("title"),
        job.get("company"),
        job.get("location"),
        job.get("description"),
        job.get("summary"),
        job.get("requirements"),
        job.get("tags"),
    )


def _profile_salary_min(profile: Dict[str, Any]) -> int | None:
    return _salary_number(
        profile.get("minimum_salary_aed")
        or profile.get("salary_minimum_aed")
        or profile.get("salary_expectation_aed")
    )


def _role_match(job: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    title = str(job.get("title") or "").lower()
    target_roles = _as_list(profile.get("target_roles"))
    return bool(target_roles and _contains_any(title, target_roles))


def _location_match(job: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    location = str(job.get("location") or job.get("city") or "").lower()
    cities = _as_list(profile.get("preferred_cities") or profile.get("preferred_city"))
    return bool(location and cities and _contains_any(location, cities))


def _location_mismatch(job: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    location = str(job.get("location") or job.get("city") or "").lower()
    cities = _as_list(profile.get("preferred_cities") or profile.get("preferred_city"))
    if not location or not cities:
        return False
    if "remote" in location or "uae" in location:
        return False
    return not _contains_any(location, cities)


def _skill_overlap(job: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
    skills = _as_list(profile.get("skills"))
    text = _job_text(job)
    matches = [skill for skill in skills if len(skill) > 2 and skill.lower() in text]
    return matches[:5]


def _seniority_mismatch(job: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    title = str(job.get("title") or "").lower()
    years = profile.get("years_experience") or profile.get("years_experience_hint")
    try:
        years_num = float(years) if years is not None else None
    except (TypeError, ValueError):
        years_num = None
    if years_num is None:
        return False
    is_senior_job = any(term in title for term in _SENIOR_TERMS)
    is_junior_job = any(term in title for term in _JUNIOR_TERMS)
    return (is_senior_job and years_num < 3) or (is_junior_job and years_num >= 8)


def _missing_facts(job: Dict[str, Any]) -> List[str]:
    facts: List[str] = []
    text = _job_text(job)
    if not _has_salary(job):
        facts.append("salary range")
    if "visa" not in text and "sponsor" not in text and "work permit" not in text:
        facts.append("visa requirements")
    if not any(term in text for term in ["experience", "years", "senior", "junior", "manager", "lead"]):
        facts.append("experience level")
    if not any(term in text for term in ["english", "arabic", "bilingual", "language"]):
        facts.append("language requirements")
    return facts[:3]


def calculate_confidence(
    match_reasons: List[str],
    match_concerns: List[str],
    missing_facts: List[str],
    *,
    major_red_flags: int = 0,
) -> Confidence:
    """Return Rico's confidence in recommendation quality, not hiring odds."""
    if major_red_flags > 0:
        return "low"
    if len(missing_facts) >= 3:
        return "low"
    if len(match_reasons) >= 3 and len(match_concerns) == 0 and len(missing_facts) <= 1:
        return "high"
    return "medium"


def build_recommended_action(
    confidence: Confidence,
    match_concerns: List[str],
    missing_facts: List[str],
) -> str:
    if confidence == "high":
        return "Review the role and prepare a tailored application before applying."
    if confidence == "low":
        return "Review the risk areas before applying so you do not spend energy blindly."
    if missing_facts:
        return "Review the missing details, then decide whether to prepare an application."
    if match_concerns:
        return "Check the flagged items before applying."
    return "Review the role and ask Rico to prepare your application if it still feels right."


def build_match_explanation(job: Dict[str, Any], profile: Any | None) -> Dict[str, Any]:
    """Build Rico's v1 structured match explanation.

    Returns exactly:
      confidence, match_reasons, match_concerns, missing_facts,
      recommended_action
    """
    job_data = _to_dict(job)
    profile_data = _to_dict(profile)
    title = str(job_data.get("title") or "This role")
    location = str(job_data.get("location") or job_data.get("city") or "")
    match_reasons: List[str] = []
    match_concerns: List[str] = []
    major_red_flags = 0

    if _role_match(job_data, profile_data):
        match_reasons.append("The role title matches your target role.")
    elif _as_list(profile_data.get("target_roles")):
        match_concerns.append("The role title does not clearly match your target roles.")
        major_red_flags += 1
    else:
        match_concerns.append("Your target role is not fully set yet.")

    if _location_match(job_data, profile_data):
        match_reasons.append("The location matches one of your preferred cities.")
    elif _location_mismatch(job_data, profile_data):
        match_concerns.append("The location appears outside your preferred cities.")
        major_red_flags += 1
    elif location:
        match_reasons.append("The job location is available for review.")

    skills = _skill_overlap(job_data, profile_data)
    if skills:
        shown = ", ".join(skills[:3])
        match_reasons.append(f"Your profile includes relevant skills: {shown}.")
    elif _as_list(profile_data.get("skills")):
        match_concerns.append("The job text does not clearly show your strongest skills.")

    salary_min = _profile_salary_min(profile_data)
    salary_seen = _salary_number(_salary_text(job_data))
    if salary_min and salary_seen:
        if salary_seen >= salary_min:
            match_reasons.append("The listed salary appears aligned with your minimum target.")
        else:
            match_concerns.append("The listed salary appears below your minimum target.")
            major_red_flags += 1

    if _seniority_mismatch(job_data, profile_data):
        match_concerns.append("The seniority level may not match your experience profile.")
        major_red_flags += 1

    missing = _missing_facts(job_data)
    confidence = calculate_confidence(
        match_reasons,
        match_concerns,
        missing,
        major_red_flags=major_red_flags,
    )

    if not match_reasons:
        match_reasons.append(f"{title} may still be worth reviewing if it matches your goals.")

    return {
        "confidence": confidence,
        "match_reasons": match_reasons[:3],
        "match_concerns": match_concerns[:3],
        "missing_facts": missing[:3],
        "recommended_action": build_recommended_action(confidence, match_concerns, missing),
    }
