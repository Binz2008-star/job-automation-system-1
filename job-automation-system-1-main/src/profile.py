"""
Roben Edwan's Candidate Profile System
Optimized for HSE / QHSE / EHS / ESG / Compliance roles in UAE.
"""

CANDIDATE_PROFILE = {
    "name": "Roben Edwan - HSE & Compliance Professional",
    "experience_years": 8,
    "location": "UAE",
    "target_roles": [
        "HSE Manager",
        "QHSE Manager",
        "EHS Manager",
        "HSE Officer",
        "Safety Manager",
        "Environmental Manager",
        "Compliance Manager",
        "ESG Manager",
        "Health Safety Environment Manager",
        "Quality Health Safety Environment Manager",
        "HSE Advisor",
        "HSE Coordinator",
        "HSE Supervisor"
    ],
    "skills": {
        "hse_core": {
            "keywords": [
                "hse", "health safety environment", "health and safety",
                "safety management", "occupational health", "workplace safety",
                "incident management", "accident investigation", "risk assessment",
                "hazard identification", "safety procedures", "safety protocols"
            ],
            "weight": 18,
            "experience_years": 5
        },
        "environmental": {
            "keywords": [
                "environmental management", "environmental impact", "environmental compliance",
                "sustainability", "waste management", "pollution control",
                "environmental monitoring", "environmental regulations", "green building",
                "carbon footprint", "ems", "environmental management system"
            ],
            "weight": 14,
            "experience_years": 4
        },
        "compliance_governance": {
            "keywords": [
                "compliance", "governance", "audit", "regulatory compliance",
                "iso standards", "iso 9001", "iso 14001", "iso 45001",
                "internal audit", "external audit", "policy compliance",
                "legal compliance", "quality management", "quality assurance"
            ],
            "weight": 15,
            "experience_years": 4
        },
        "risk_management": {
            "keywords": [
                "risk management", "risk assessment", "risk mitigation",
                "operational risk", "safety risk", "environmental risk",
                "hira", "job hazard analysis", "risk register",
                "risk control measures", "incident prevention"
            ],
            "weight": 12,
            "experience_years": 3
        },
        "uae_experience": {
            "keywords": ["uae", "dubai", "abu dhabi", "middle east", "gcc", "local market"],
            "weight": 10,
            "experience_years": 4
        },
        "leadership": {
            "keywords": [
                "team management", "team leadership", "supervision",
                "stakeholder management", "training", "hse training",
                "safety culture", "leadership", "management"
            ],
            "weight": 11,
            "experience_years": 5
        }
    },
    "hard_reject_keywords": [
        # Medical/Healthcare
        "doctor", "nurse", "physician", "surgeon", "medical",
        "healthcare", "hospital", "clinic", "pharmacy", "pharmacist",
        "cardiology", "obstetrics", "gynecology", "pediatrics", "endocrinology",

        # Technical/Engineering (non-HSE)
        "software engineer", "developer", "programmer", "it support",
        "technical support", "network engineer", "system administrator",
        "data scientist", "machine learning", "ai engineer",

        # Sales/Marketing
        "sales executive", "sales manager", "business development",
        "business development manager", "marketing", "digital marketing",
        "telesales", "call center", "customer service",

        # Administrative/Clerical
        "receptionist", "front desk", "admin assistant", "office assistant",
        "secretary", "data entry", "office clerk",

        # Construction (non-HSE roles)
        "architect", "civil engineer", "structural engineer",
        "electrical engineer", "mechanical engineer",
        "site engineer", "project engineer", "quantity surveyor",
        "fit-out", "interior designer", "ff&e designer",

        # Logistics/Operations (non-HSE)
        "driver", "delivery driver", "truck driver",
        "warehouse", "warehouse manager", "logistics coordinator",
        "supply chain", "procurement", "purchasing",

        # Hospitality/Retail
        "waiter", "waitress", "bartender", "chef", "cook",
        "retail", "store manager", "sales associate",

        # Low-level roles
        "junior", "entry level", "internship", "trainee", "fresh graduate",
        "assistant", "coordinator", "administrator", "clerk"
    ],
    "seniority_keywords": [
        "senior", "lead", "head", "manager", "director", "vp", "vice president",
        "chief", "c-level", "strategic", "leadership"
    ],
    "location_preferences": {
        "dubai": 25,
        "abu dhabi": 20,
        "sharjah": 15,
        "ajman": 15,
        "uae remote": 10,
        "uae hybrid": 10
    },
    "salary_range": {
        "min": 25000,
        "max": 30000,
        "currency": "AED",
        "preferred_keywords": ["25k", "30k", "25000", "30000"]
    },
    "preferred_companies": [],
    "blacklisted_companies": []
}


def get_candidate_profile():
    """Return Roben Edwan's candidate profile."""
    return CANDIDATE_PROFILE


def get_target_roles():
    """Return Roben's target roles list."""
    return get_candidate_profile()["target_roles"]


def get_skill_weights():
    """Return skill categories with their weights."""
    profile = get_candidate_profile()
    return {skill: data["weight"] for skill, data in profile["skills"].items()}


def get_hard_reject_keywords():
    """Return keywords that should result in immediate disqualification."""
    return get_candidate_profile()["hard_reject_keywords"]


def get_seniority_keywords():
    """Return keywords indicating senior-level positions."""
    return get_candidate_profile()["seniority_keywords"]


def get_location_preferences():
    """Return location-based scoring preferences."""
    return get_candidate_profile()["location_preferences"]


def get_salary_preferences():
    """Return salary-based scoring preferences."""
    return get_candidate_profile()["salary_range"]


def calculate_experience_match(skill_category, job_text):
    """Calculate experience bonus for matching skill category."""
    profile = get_candidate_profile()
    if skill_category not in profile["skills"]:
        return 0

    skill_data = profile["skills"][skill_category]
    required_years = skill_data["experience_years"]
    candidate_years = profile["experience_years"]

    # Bonus if candidate has sufficient experience
    if candidate_years >= required_years:
        return min(5, candidate_years - required_years)
    return 0


def get_profile_match_explanation(job, score_details):
    """Generate profile-specific explanation for why job matches Roben's profile."""
    title = str(job.get('title', '')).lower()
    description = str(job.get('description', '')).lower()

    explanations = []

    # Check for target role matches
    for role in get_target_roles():
        if role.lower() in title:
            explanations.append(f"Direct match for target role: {role}")
            break

    # Check for key skill matches
    if "hse" in title and "manager" in title:
        explanations.append("Strong HSE management alignment")

    if "qhse" in title:
        explanations.append("Quality HSE specialization")

    if "safety" in title and "manager" in title:
        explanations.append("Safety management expertise match")

    if "environmental" in title:
        explanations.append("Environmental management experience")

    if "compliance" in title:
        explanations.append("Compliance and governance experience")

    if "esg" in title:
        explanations.append("ESG and sustainability focus")

    if "uae" in description or "dubai" in description:
        explanations.append("UAE market experience required")

    if not explanations:
        explanations.append("Relevant HSE/Compliance experience")

    return " | ".join(explanations[:3])  # Limit to top 3 reasons
