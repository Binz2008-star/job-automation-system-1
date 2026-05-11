"""Rule-based match explanation builder for Rico companion intelligence.

This module generates structured, fact-based explanations for why a job matches
a user's profile, what concerns exist, what facts are missing, and what the
recommended next action should be.

This is rule-based (not AI-dependent) for predictability, testability, and
to avoid hallucinations. The logic can be enhanced with AI later for wording.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_match_explanation(job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Generate structured match explanation using rule-based logic.

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
        - confidence: "high" | "medium" | "low"
    """
    match_reasons: List[str] = []
    match_concerns: List[str] = []
    missing_facts: List[str] = []

    job_title = str(job.get("title", "")).lower()
    job_description = str(job.get("description", "")).lower()
    job_location = str(job.get("location", job.get("city", ""))).lower()
    job_salary = job.get("salary") or job.get("salary_range")
    job_combined = f"{job_title} {job_description} {job_location}"

    target_roles = profile.get("target_roles", [])
    preferred_cities = profile.get("preferred_cities", [])
    skills = profile.get("skills", [])
    salary_expectation = profile.get("salary_expectation_aed")
    minimum_salary = profile.get("minimum_salary_aed")
    visa_status = profile.get("visa_status")
    languages = profile.get("languages", [])
    years_experience = profile.get("years_experience")

    # Check role match
    for role in target_roles:
        if role.lower() in job_title or role.lower() in job_description:
            match_reasons.append(f"The job title matches your target role: {role}")

    # Check location match
    for city in preferred_cities:
        if city.lower() in job_location:
            match_reasons.append(f"The location is one of your preferred cities: {city}")

    # Check skills match
    matched_skills = []
    for skill in skills:
        if skill.lower() in job_description:
            matched_skills.append(skill)
    if matched_skills:
        match_reasons.append(f"Your CV includes relevant skills: {', '.join(matched_skills[:3])}")

    # Check salary alignment
    if job_salary and salary_expectation:
        # Try to extract numeric value from salary string
        salary_str = str(job_salary).lower()
        if "aed" in salary_str or "aED" in salary_str or "aed" in salary_str:
            # Simple extraction - in production would use more robust parsing
            import re
            numbers = re.findall(r'\d+', salary_str)
            if numbers:
                max_salary = max(map(int, numbers))
                if minimum_salary and max_salary >= minimum_salary:
                    match_reasons.append(f"Salary range appears aligned with your minimum target")
                else:
                    match_concerns.append(f"Salary may be below your minimum expectation")
    elif not job_salary:
        missing_facts.append("salary range")
        match_concerns.append("The salary is not listed")

    # Check visa status
    if visa_status and "visa" in job_combined.lower():
        if "sponsor" in job_combined.lower():
            match_reasons.append("Visa sponsorship appears to be offered")
        else:
            match_concerns.append("Visa support is unclear")
    elif not job_salary:
        missing_facts.append("visa requirements")

    # Check language requirements
    for language in languages:
        if language.lower() in job_description:
            match_reasons.append(f"Job requires {language}, which is in your profile")
    if "arabic" in job_description and "arabic" not in [l.lower() for l in languages]:
        match_concerns.append("The role asks for Arabic, which is not confirmed in your profile")
        missing_facts.append("language requirements")

    # Check experience level
    if years_experience:
        if "senior" in job_title and years_experience < 5:
            match_concerns.append("Senior role may require more experience than you have")
        elif "junior" in job_title and years_experience > 5:
            match_concerns.append("Junior role may be below your experience level")

    # Calculate confidence
    reason_count = len(match_reasons)
    concern_count = len(match_concerns)
    missing_count = len(missing_facts)

    if reason_count >= 3 and concern_count <= 1:
        confidence = "high"
    elif reason_count >= 2 and concern_count <= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # Determine recommended action
    if confidence == "high" and concern_count == 0:
        recommended_action = "This is a strong match. Consider applying now or preparing a tailored CV."
    elif confidence == "high" and concern_count > 0:
        recommended_action = "Save this job and verify the concerns before applying. Let me tailor your CV first."
    elif confidence == "medium":
        recommended_action = "Save this job and let me tailor your CV before applying. Verify salary and visa if critical."
    else:
        recommended_action = "Review carefully. This may not be the best fit. Consider skipping unless specific criteria match."

    return {
        "match_reasons": match_reasons,
        "match_concerns": match_concerns,
        "missing_facts": missing_facts,
        "recommended_action": recommended_action,
        "confidence": confidence,
    }
