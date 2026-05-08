import re
import os
from src.profile import get_candidate_profile, get_skill_weights, get_negative_keywords, get_seniority_keywords, calculate_experience_match, get_location_preferences, get_salary_preferences, get_target_roles, get_profile_match_explanation


def score_job(job):
    """
    Roben Edwan's CV-aware job scoring system.
    Optimized for executive operations and founder office roles in UAE.
    """
    score = 0
    score_details = []

    # Extract job text for analysis
    title = str(job.get("title", "")).lower()
    description = str(job.get("description", "")).lower()
    job_text = f"{title} {description}"

    # 0. Hard exclusion keywords - immediate disqualification
    exclude_keywords_str = os.getenv("EXCLUDE_KEYWORDS", "")
    exclude_keywords = [kw.strip().lower() for kw in exclude_keywords_str.split(",") if kw.strip()]
    if exclude_keywords:
        exclude_matches = [kw for kw in exclude_keywords if kw in job_text]
        if exclude_matches:
            # Hard penalty - make score very low
            score = -50
            score_details.append(f"Excluded: {exclude_matches} (-50)")
            job["score"] = score
            job["score_details"] = score_details
            return score

    profile = get_candidate_profile()
    skill_weights = get_skill_weights()
    negative_keywords = get_negative_keywords()
    seniority_keywords = get_seniority_keywords()
    location_preferences = get_location_preferences()
    salary_preferences = get_salary_preferences()
    target_roles = [role.lower() for role in get_target_roles()]

    # 0.5. Positive target role filtering - only HSE/Safety/Compliance roles
    positive_target_keywords = [
        "hse", "qhse", "ehs", "safety", "environmental", "compliance",
        "health", "safety officer", "safety manager", "environmental manager",
        "compliance officer", "risk manager", "auditor", "quality", "qms"
    ]

    positive_match = any(kw in title for kw in positive_target_keywords)
    if not positive_match:
        # No positive target keywords - significantly reduce score
        score -= 30
        score_details.append("No HSE/Safety keywords (-30)")

    # 1. Target role matching (highest priority)
    for role in target_roles:
        if role in title:
            role_bonus = 25
            score += role_bonus
            score_details.append(f"Target role: {role} (+{role_bonus})")
            break

    # 2. Heavy negative keyword penalties
    negative_matches = [kw for kw in negative_keywords if kw in job_text]
    if negative_matches:
        penalty = len(negative_matches) * 25  # Heavier penalties
        score -= penalty
        score_details.append(f"Negative keywords: {negative_matches} (-{penalty})")

    # 3. Skill-based scoring with Roben's weights
    matched_skills = []
    for skill_category, skill_data in profile["skills"].items():
        keywords = skill_data["keywords"]
        weight = skill_data["weight"]

        # Check for keyword matches
        skill_matches = [kw for kw in keywords if kw in job_text]
        if skill_matches:
            # Base score for skill match
            skill_score = len(skill_matches) * weight

            # Bonus for multiple keywords in same category
            if len(skill_matches) > 1:
                skill_score += (len(skill_matches) - 1) * (weight // 2)

            # Experience bonus
            exp_bonus = calculate_experience_match(skill_category, job_text)
            skill_score += exp_bonus

            score += skill_score
            matched_skills.append(f"{skill_category}: {skill_matches} (+{skill_score})")

    if matched_skills:
        score_details.extend(matched_skills)

    # 4. Seniority bonus
    seniority_matches = [kw for kw in seniority_keywords if kw in title]
    if seniority_matches:
        seniority_bonus = len(seniority_matches) * 8
        score += seniority_bonus
        score_details.append(f"Seniority: {seniority_matches} (+{seniority_bonus})")

    # 5. Location-based scoring (UAE preference)
    location = str(job.get("location", "")).lower()
    location_bonus = 0
    for loc, bonus in location_preferences.items():
        if loc in location or loc in job_text:
            location_bonus = bonus
            score_details.append(f"Location: {loc} (+{bonus})")
            break

    if location_bonus:
        score += location_bonus

    # 6. Salary preference bonus
    salary_keywords = salary_preferences["preferred_keywords"]
    salary_matches = [kw for kw in salary_keywords if kw in job_text]
    if salary_matches:
        salary_bonus = 10
        score += salary_bonus
        score_details.append(f"Salary preference: {salary_matches} (+{salary_bonus})")

    # 7. Specific role bonuses
    if "executive assistant to ceo" in title:
        exec_bonus = 20
        score += exec_bonus
        score_details.append(f"Executive Assistant to CEO (+{exec_bonus})")

    if "chief of staff" in title:
        cos_bonus = 18
        score += cos_bonus
        score_details.append(f"Chief of Staff (+{cos_bonus})")

    if "founder office" in title:
        founder_bonus = 15
        score += founder_bonus
        score_details.append(f"Founder Office (+{founder_bonus})")

    # 8. Minimum score threshold
    if score < 0:
        score = 0

    # Store scoring details and profile explanation
    job["score_details"] = score_details
    job["profile_explanation"] = get_profile_match_explanation(job, score_details)

    return score


def get_score_explanation(job):
    """Return human-readable explanation of job score."""
    if "score_details" in job:
        return " | ".join(job["score_details"])
    return "No scoring details available"


def get_profile_explanation(job):
    """Return profile-specific explanation for why job matches Roben."""
    return job.get("profile_explanation", "Relevant executive operations experience")
