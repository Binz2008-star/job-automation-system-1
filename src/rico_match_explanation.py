"""Rule-based match explanation builder for Rico companion intelligence.

This module generates structured, fact-based explanations for why a job matches
a user's profile, what concerns exist, what facts are missing, and what the
recommended next action should be.

This is rule-based (not AI-dependent) for predictability, testability, and
to avoid hallucinations. The logic can be enhanced with AI later for wording.

PHILOSOPHY:
- Confidence = Rico's confidence in recommendation quality (fit quality), NOT hiring probability
- Major red flags override optimistic scores
- Confidence label > raw score (confidence is Rico's final judgment)
- Three tiers only: High, Medium, Low (no fake precision)
- High confidence must be earned (strong fit + low uncertainty + no critical missing facts)
- Low confidence triggers automatically on major mismatches
- Medium confidence is default (useful signals but review carefully)
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _detect_critical_red_flags(job: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
    """Detect critical red flags that should override optimistic scores.

    These force Low confidence regardless of numerical score because Rico's
    philosophy is: do not encourage unrealistic applications.

    Returns:
        List of critical red flag descriptions
    """
    red_flags: List[str] = []

    job_title = str(job.get("title", "")).lower()
    job_description = str(job.get("description", "")).lower()
    job_location = str(job.get("location", job.get("city", ""))).lower()
    job_salary = job.get("salary") or job.get("salary_range")
    job_combined = f"{job_title} {job_description} {job_location}"

    target_roles = profile.get("target_roles", [])
    preferred_cities = profile.get("preferred_cities", [])
    minimum_salary = profile.get("minimum_salary_aed")
    visa_status = profile.get("visa_status")
    years_experience = profile.get("years_experience")

    # Salary below minimum
    if job_salary and minimum_salary:
        salary_str = str(job_salary).lower()
        if "aed" in salary_str:
            import re
            numbers = re.findall(r'\d+', salary_str)
            if numbers:
                max_salary = max(map(int, numbers))
                if max_salary < minimum_salary:
                    red_flags.append(f"Salary ({max_salary}) is below your minimum ({minimum_salary})")

    # Major location mismatch
    if preferred_cities:
        has_location_match = any(city.lower() in job_location for city in preferred_cities)
        if not has_location_match and job_location and "remote" not in job_location:
            red_flags.append(f"Location ({job_location}) is not in your preferred cities")

    # Role mismatch
    if target_roles:
        has_role_match = any(role.lower() in job_title or role.lower() in job_description for role in target_roles)
        if not has_role_match:
            red_flags.append(f"Job title does not match your target roles")

    # Visa conflict
    if visa_status and "visa" in job_combined.lower():
        if "sponsor" not in job_combined.lower() and visa_status.lower() in ["needs sponsorship", "requires visa"]:
            red_flags.append("Visa sponsorship not mentioned but you require it")

    # Strong seniority mismatch
    if years_experience:
        if "senior" in job_title and years_experience < 3:
            red_flags.append(f"Senior role requires more experience (you have {years_experience} years)")
        elif "junior" in job_title and years_experience > 7:
            red_flags.append(f"Junior role may be below your experience level (you have {years_experience} years)")

    return red_flags


def _detect_positive_fit_signals(job: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
    """Detect positive fit signals that support a recommendation.

    Returns:
        List of positive signal descriptions
    """
    signals: List[str] = []

    job_title = str(job.get("title", "")).lower()
    job_description = str(job.get("description", "")).lower()
    job_location = str(job.get("location", job.get("city", ""))).lower()
    job_salary = job.get("salary") or job.get("salary_range")

    target_roles = profile.get("target_roles", [])
    preferred_cities = profile.get("preferred_cities", [])
    skills = profile.get("skills", [])
    salary_expectation = profile.get("salary_expectation_aed")
    languages = profile.get("languages", [])

    # Role match
    for role in target_roles:
        if role.lower() in job_title:
            signals.append(f"Job title matches target role: {role}")

    # Location match
    for city in preferred_cities:
        if city.lower() in job_location:
            signals.append(f"Location matches preference: {city}")

    # Skills overlap
    matched_skills = [skill for skill in skills if skill.lower() in job_description]
    if matched_skills:
        signals.append(f"Skills overlap: {', '.join(matched_skills[:3])}")

    # Salary alignment
    if job_salary and salary_expectation:
        signals.append("Salary information available and within range")

    # Language match
    for language in languages:
        if language.lower() in job_description:
            signals.append(f"Language requirement met: {language}")

    return signals


def _detect_missing_critical_facts(job: Dict[str, Any]) -> List[str]:
    """Detect missing critical facts that should prevent High confidence.

    Critical facts: salary, visa, work authorization, seniority, language requirements.

    Returns:
        List of missing critical fact descriptions
    """
    missing: List[str] = []

    job_title = str(job.get("title", "")).lower()
    job_description = str(job.get("description", "")).lower()
    job_salary = job.get("salary") or job.get("salary_range")

    # Salary missing
    if not job_salary:
        missing.append("salary range")

    # Visa/work authorization
    job_combined = f"{job_title} {job_description}"
    if "visa" in job_combined.lower() and "sponsor" not in job_combined.lower():
        missing.append("visa sponsorship details")

    # Language requirements
    if "arabic" in job_description or "language" in job_description:
        missing.append("language requirements details")

    # Seniority/experience requirements
    if "senior" in job_title or "junior" in job_title or "experience" in job_description:
        missing.append("experience level requirements")

    return missing


def calculate_confidence(
    red_flags: List[str],
    positive_signals: List[str],
    missing_facts: List[str]
) -> Tuple[str, List[str]]:
    """Calculate confidence tier based on red flags, signals, and missing facts.

    IMPORTANT: Confidence label > raw score. This is Rico's final judgment.

    Returns:
        Tuple of (confidence_tier, concerns_list)
        confidence_tier: "high" | "medium" | "low"
    """
    concerns: List[str] = []

    # CRITICAL: Any red flag forces Low confidence
    if red_flags:
        concerns.extend(red_flags)
        return "low", concerns

    # CRITICAL: Too many missing critical facts prevents High confidence
    critical_missing = [f for f in missing_facts if f in ["salary range", "visa sponsorship details"]]
    if len(critical_missing) >= 2:
        concerns.append(f"Critical information missing: {', '.join(critical_missing)}")
        return "low", concerns

    # High confidence: strong signals + low uncertainty
    # Requires: at least 3 positive signals + no more than 1 missing fact
    if len(positive_signals) >= 3 and len(missing_facts) <= 1:
        return "high", concerns

    # Medium confidence: some signals but review needed
    # Default tier for most jobs
    if len(positive_signals) >= 2:
        if missing_facts:
            concerns.append(f"Some details unclear: {', '.join(missing_facts[:2])}")
        return "medium", concerns

    # Low confidence: weak signals or too uncertain
    if missing_facts:
        concerns.append(f"Too much information missing: {', '.join(missing_facts)}")
    else:
        concerns.append("Limited fit signals detected")
    return "low", concerns


def build_match_explanation(job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Generate structured match explanation using rule-based logic.

    IMPORTANT: Confidence represents Rico's confidence in the recommendation quality
    (how well this job fits the user's profile), NOT the user's chance of getting hired.
    High confidence means "this appears to be a worthwhile opportunity," not "you will get the job."

    Args:
        job: Job dictionary with title, company, location, description, salary, etc.
        profile: User profile dictionary with target_roles, preferred_cities,
                 skills, salary_expectation_aed, minimum_salary_aed, visa_status, etc.

    Returns:
        Dictionary with:
        - match_reasons: List of reasons why this job fits
        - match_concerns: List of concerns or risks
        - missing_facts: List of missing information from the job posting
        - recommended_action: What the user should do next
        - confidence: "high" | "medium" | "low" (tiered, not percentage-based)
    """
    # Step 1: Detect critical red flags (override optimistic scores)
    red_flags = _detect_critical_red_flags(job, profile)

    # Step 2: Detect positive fit signals
    positive_signals = _detect_positive_fit_signals(job, profile)

    # Step 3: Detect missing critical facts
    missing_facts = _detect_missing_critical_facts(job)

    # Step 4: Calculate confidence (red flags > signals > missing facts)
    confidence, concerns = calculate_confidence(red_flags, positive_signals, missing_facts)

    # Step 5: Determine recommended action with Rico's trust tone
    if confidence == "high":
        recommended_action = "This looks like a strong fit based on your role, skills, and preferred location. The available information supports moving forward."
    elif confidence == "medium":
        recommended_action = "This role looks promising, but some important details are unclear. Review carefully before applying."
    else:  # low
        recommended_action = "This role has meaningful risks or missing information. Do not apply blindly until these concerns are clarified."

    return {
        "match_reasons": positive_signals,
        "match_concerns": concerns,
        "missing_facts": missing_facts,
        "recommended_action": recommended_action,
        "confidence": confidence,
    }
