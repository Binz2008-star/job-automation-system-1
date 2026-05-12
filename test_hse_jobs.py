#!/usr/bin/env python3
"""
Test job processing with HSE-specialized jobs vs irrelevant jobs.
Validates positive-match detection and learning signal recording.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.decision_engine import JobDecisionEngine
from src.profile import get_candidate_profile, get_target_roles
from src.repositories.learning_repo import get_learning_repository
from src.llm_scorer import score_jobs_llm   # uses OpenAI if available, else keyword fallback

# Sample jobs: 3 non‑HSE (already tested) + 3 HSE
sample_jobs = [
    # Non‑HSE (should be skipped)
    {
        "title": "Head-Facilities Management",
        "company": "Transguard Group",
        "location": "AE",
        "description": "Facilities management and Transguard Living team in Dubai...",
        "link": "https://ae.indeed.com/viewjob?jk=163602e496567ff9",
    },
    {
        "title": "Finance Manager",
        "company": "Chalhoub Group",
        "location": "Dubai, DU, AE",
        "description": "Luxury retail finance...",
        "link": "https://ae.indeed.com/viewjob?jk=cc69f8ad01c71cc4",
    },
    {
        "title": "Senior Soft Mobility & Landscape Designer",
        "company": "SYSTRA",
        "location": "Dubai, DU, AE",
        "description": "Sustainable mobility design...",
        "link": "https://ae.indeed.com/viewjob?jk=c83e3ac1d081d6b1",
    },
    # HSE jobs (expected APPLY or WATCH)
    {
        "title": "HSE Manager - Oil & Gas",
        "company": "ADNOC",
        "location": "Abu Dhabi, UAE",
        "description": "Health, Safety and Environment manager required for oil and gas operations. NEBOSH, ISO 45001, incident investigation, risk assessment.",
        "link": "https://example.com/hse-manager",
    },
    {
        "title": "QHSE Officer - Construction",
        "company": "ALEC Engineering",
        "location": "Dubai, UAE",
        "description": "QHSE officer needed for construction site safety, audits, toolbox talks, permits, risk assessments, and compliance.",
        "link": "https://example.com/qhse-officer",
    },
    {
        "title": "EHS Specialist - Manufacturing",
        "company": "Emirates Global Aluminium",
        "location": "UAE",
        "description": "EHS specialist responsible for environmental health and safety programs, safety inspections, incident reporting, and regulatory compliance.",
        "link": "https://example.com/ehs-specialist",
    },
]

def get_pipeline_decision(score: int, probability: float, min_score: int = 50) -> str:
    if score >= min_score and probability >= 50:
        return "APPLY"
    elif score >= min_score - 15 and probability >= 35:
        return "WATCH"
    else:
        return "SKIP"

def main():
    print("=" * 80)
    print("JOB PROCESSING TEST – HSE vs Non‑HSE")
    print("=" * 80)

    # Load candidate profile & target roles (should be HSE-focused)
    profile = get_candidate_profile()
    target_roles = get_target_roles()
    print(f"\n📋 Target roles: {', '.join(target_roles)}")
    print(f"📋 Experience: {profile.get('experience_years', '?')} years\n")

    # Initialize decision engine
    engine = JobDecisionEngine.from_loaders(
        lambda: profile,
        lambda: target_roles
    )

    # Score jobs (LLM or keyword fallback)
    print("🔍 Scoring jobs...")
    scored_jobs = score_jobs_llm(sample_jobs)
    for job in scored_jobs:
        job["score"] = job.get("score", 0)

    # Learning repo setup
    repo = get_learning_repository()
    user_id = "test_hse_user"

    decisions = []
    for job in scored_jobs:
        score = job["score"]
        prob_result = engine.calculate_success_probability(job)
        prob = prob_result.probability
        decision = get_pipeline_decision(score, prob)

        # Determine learning weight
        if decision == "APPLY":
            weight = 0.7
        elif decision == "WATCH":
            weight = 0.2
        else:
            weight = -0.3

        # Record learning signal
        repo.record_signal(
            canonical_user_id=user_id,
            signal_type="role_preference",
            signal_value=job["title"],
            signal_weight=weight,
            source="test_script",
            metadata={"decision": decision, "score": score, "probability": prob}
        )

        decisions.append((job, score, prob, decision, weight))

        # Print details
        print(f"\n{'─'*60}")
        print(f"📌 {job['title']} @ {job['company']}")
        print(f"   Score: {score}")
        print(f"   Probability: {prob:.1f}% ({prob_result.confidence})")
        print(f"   Decision: {decision}")
        print(f"   Learning weight: {weight}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total jobs processed: {len(scored_jobs)}")
    print(f"APPLY decisions: {sum(1 for _,_,_,d,_ in decisions if d == 'APPLY')}")
    print(f"WATCH decisions: {sum(1 for _,_,_,d,_ in decisions if d == 'WATCH')}")
    print(f"SKIP decisions:  {sum(1 for _,_,_,d,_ in decisions if d == 'SKIP')}")

    # Show learning profile after this test
    profile_learn = repo.get_learning_profile(user_id)
    print("\n📚 Learning profile (top role preferences):")
    for role, w in sorted(profile_learn.role_preferences.items(), key=lambda x: -abs(x[1]))[:5]:
        print(f"   {role[:50]:50} {w:+.2f}")

    print("\n✅ Test complete. Learning signals persisted.")

if __name__ == "__main__":
    main()
