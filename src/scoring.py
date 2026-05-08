import os
from src.profile import (
    get_candidate_profile, get_skill_weights, get_hard_reject_keywords,
    get_seniority_keywords, calculate_experience_match, get_location_preferences,
    get_salary_preferences, get_target_roles, get_profile_match_explanation
)


def score_job(job):
    """
    Roben Edwan's CV-aware job scoring system.
    Optimized for HSE / QHSE / EHS / ESG / Compliance roles in UAE.

    Pipeline: type-guard → ENV excludes → hard reject → title gate → scoring → floor 0
    """
    # Guard: reject non-dict input gracefully instead of raising AttributeError
    if not isinstance(job, dict):
        return 0

    score = 0
    score_details = []

    # Extract job text for analysis
    title = str(job.get("title", "") or "").lower()
    description = str(job.get("description", "") or "").lower()
    job_text = f"{title} {description}"

    # STEP 0: ENV excludes - immediate disqualification
    exclude_keywords_str = os.getenv("EXCLUDE_KEYWORDS", "")
    exclude_keywords = [kw.strip().lower() for kw in exclude_keywords_str.split(",") if kw.strip()]
    if exclude_keywords:
        exclude_matches = [kw for kw in exclude_keywords if kw in job_text]
        if exclude_matches:
            job["score"] = 0
            job["score_details"] = [f"Hard reject (ENV): {exclude_matches}"]
            job["hard_reject_reason"] = f"ENV exclude: {exclude_matches}"
            return 0

    # STEP 1: Hard reject keywords - immediate disqualification
    # These keywords only reject when found in the job title, not the description
    TITLE_ONLY_REJECT_KEYWORDS = {"civil engineer", "site engineer", "quantity surveyor", "architect"}
    hard_reject_keywords = get_hard_reject_keywords()
    hard_reject_matches = []
    for kw in hard_reject_keywords:
        text = title if kw in TITLE_ONLY_REJECT_KEYWORDS else job_text
        if f" {kw} " in f" {text} " or text.startswith(kw):
            hard_reject_matches.append(kw)
    if hard_reject_matches:
        job["score"] = 0
        job["score_details"] = [f"Hard reject: {hard_reject_matches[:3]}"]
        job["hard_reject_reason"] = f"Hard reject: {hard_reject_matches[:3]}"
        return 0

    # STEP 2: Title gate - Primary HSE vs Secondary governance signals
    PRIMARY_HSE_SIGNALS = [
        "hse", "qhse", "ehs", "hsse", "safety", "environmental", "environment",
        "esg", "sustainability"
    ]

    SECONDARY_SIGNALS = [
        "compliance", "risk", "audit", "quality", "qms", "iso"
    ]

    primary_hit = any(k in title for k in PRIMARY_HSE_SIGNALS)
    secondary_hit = any(k in title for k in SECONDARY_SIGNALS)

    profile = get_candidate_profile()
    skill_weights = get_skill_weights()
    seniority_keywords = get_seniority_keywords()
    location_preferences = get_location_preferences()
    salary_preferences = get_salary_preferences()
    target_roles = [role.lower() for role in get_target_roles()]

    # STEP 3: Target role matching (highest priority)
    for role in target_roles:
        if role in title:
            role_bonus = 25
            score += role_bonus
            score_details.append(f"Target role: {role} (+{role_bonus})")
            break

    # STEP 4: Skill-based scoring with Roben's weights
    matched_skills = []
    for skill_category, skill_data in profile["skills"].items():
        keywords = skill_data["keywords"]
        weight = skill_data["weight"]

        # Skip operations_management if no primary HSE signal
        if skill_category == "leadership" and not primary_hit:
            continue

        # Check for keyword matches (use set to avoid keyword explosion)
        skill_matches = list(set(kw for kw in keywords if kw in job_text))
        if skill_matches:
            # Base score for skill match
            skill_score = len(skill_matches) * weight

            # Bonus for multiple keywords in same category
            if len(skill_matches) > 1:
                skill_score += (len(skill_matches) - 1) * (weight // 2)

            # Cap to prevent score explosion
            skill_score = min(skill_score, weight * 4)

            # Experience bonus
            exp_bonus = calculate_experience_match(skill_category, job_text)
            skill_score += exp_bonus

            score += skill_score
            matched_skills.append(f"{skill_category}: {skill_matches} (+{skill_score})")

    if matched_skills:
        score_details.extend(matched_skills)

    # STEP 5: Seniority bonus
    seniority_matches = [kw for kw in seniority_keywords if kw in title]
    if seniority_matches:
        seniority_bonus = len(seniority_matches) * 8
        score += seniority_bonus
        score_details.append(f"Seniority: {seniority_matches} (+{seniority_bonus})")

    # STEP 6: Location-based scoring (UAE preference)
    location = str(job.get("location", "")).lower()
    location_bonus = 0
    for loc, bonus in location_preferences.items():
        if loc in location or loc in job_text:
            location_bonus = bonus
            score_details.append(f"Location: {loc} (+{bonus})")
            break

    if location_bonus:
        score += location_bonus

    # STEP 7: Salary preference bonus
    salary_keywords = salary_preferences["preferred_keywords"]
    salary_matches = [kw for kw in salary_keywords if kw in job_text]
    if salary_matches:
        salary_bonus = 10
        score += salary_bonus
        score_details.append(f"Salary preference: {salary_matches} (+{salary_bonus})")

    # STEP 8: Apply multiplier based on title signal type
    if primary_hit:
        # Full score for primary HSE signals
        pass
    elif secondary_hit:
        # Heavy penalty for secondary-only signals (compliance/risk/audit without HSE)
        score = int(score * 0.25)
        score_details.append(f"Secondary signal only (0.25× multiplier)")
    else:
        # No relevant signals
        score = int(score * 0.1)
        score_details.append(f"No relevant signals (0.1× multiplier)")

    # STEP 9: Floor at 0
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
    return job.get("profile_explanation", "Relevant HSE/Compliance experience")
