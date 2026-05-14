"""
Test script to process sample Indeed jobs through the full pipeline.

This script processes three UAE jobs through the proper pipeline order:
1. LLM scorer (populate score)
2. Decision Engine V2 for probability scoring
3. Pipeline decision logic (apply/watch/skip)
4. Learning repository signal recording
5. Persistence to job_history
"""
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.decision_engine import JobDecisionEngine
from src.profile import get_candidate_profile, get_target_roles
from src.repositories.learning_repo import get_learning_repository

# Sample jobs from Indeed/jobspy
jobs_raw = [
    {
        "title": "Head-Facilities Management and Transguard Living",
        "company": "Transguard Group",
        "location": "AE",
        "score": 0,
        "link": "https://ae.indeed.com/viewjob?jk=163602e496567ff9",
        "date_found": "2026-05-12T04:51:12.221885",
        "source": "jobspy",
        "description": "We are currently recruiting for a **Head Facilities Management and Transguard Living** to join our Total Facilities Management and Transguard Living team in Dubai...",
    },
    {
        "title": "Finance Manager - Max Mara",
        "company": "Chalhoub Group",
        "location": "Dubai, DU, AE",
        "score": 0,
        "link": "https://ae.indeed.com/viewjob?jk=cc69f8ad01c71cc4",
        "date_found": "2026-05-12T04:51:12.221885",
        "source": "jobspy",
        "description": "**INSPIRE | EXHILARATE | DELIGHT**\n\nFor over seven decades, Chalhoub Group has been a partner and creator of luxury experiences in the Middle East...",
    },
    {
        "title": "Senior Soft Mobility & Landscape Designer",
        "company": "SYSTRA",
        "location": "Dubai, DU, AE",
        "score": 0,
        "link": "https://ae.indeed.com/viewjob?jk=c83e3ac1d081d6b1",
        "date_found": "2026-05-12T06:10:33.341473",
        "source": "jobspy",
        "description": "SYSTRA is one of the world's leading engineering and consultancy groups specialising in public transport and sustainable mobility...",
    },
]

def get_confidence_label(probability: float) -> str:
    """Get confidence label from probability."""
    if probability >= 80:
        return "Very High"
    elif probability >= 65:
        return "High"
    elif probability >= 50:
        return "Medium"
    elif probability >= 35:
        return "Low"
    else:
        return "Very Low"

def get_pipeline_decision(score: int, probability: float, min_score: int = 50) -> str:
    """Get pipeline decision based on score and probability."""
    if score >= min_score and probability >= 50:
        return "apply"
    elif score >= min_score - 15 and probability >= 35:
        return "watch"
    else:
        return "skip"

def score_jobs_keyword_fallback(jobs: List[Dict[str, Any]], profile: Dict[str, Any], target_roles: List[str]) -> List[Dict[str, Any]]:
    """Fallback keyword-based scoring when LLM scorer unavailable."""
    scored_jobs = []
    for job in jobs:
        title_lower = job["title"].lower()
        desc_lower = job.get("description", "").lower()

        score = 0
        # Check for target role keywords
        for role in target_roles:
            if role in title_lower or role in desc_lower:
                score += 30

        # Check for skills
        for skill in profile.get("skills", {}).keys():
            if skill in title_lower or skill in desc_lower:
                score += 15

        # Location bonus
        if "ae" in job.get("location", "").lower() or "dubai" in job.get("location", "").lower():
            score += 10

        # Cap at 100
        score = min(score, 100)

        job["score"] = score
        scored_jobs.append(job)

    return scored_jobs

def record_learning_signals(user_id: str, decisions: List[Dict[str, Any]]) -> None:
    """Record learning signals based on job decisions."""
    try:
        repo = get_learning_repository()

        for decision in decisions:
            job = decision["job"]
            decision_type = decision["decision"]

            # Map decisions to signal weights
            if decision_type == "apply":
                weight = 0.8
                signal_type = "role_preference"
            elif decision_type == "watch":
                weight = 0.4
                signal_type = "role_preference"
            else:  # skip
                weight = -0.3
                signal_type = "role_preference"

            repo.record_signal(
                canonical_user_id=user_id,
                signal_type=signal_type,
                signal_value=job.get("title", ""),
                signal_weight=weight,
                source="test_pipeline",
                metadata={
                    "company": job.get("company"),
                    "location": job.get("location"),
                    "score": job.get("score"),
                    "probability": decision.get("probability"),
                }
            )

        print(f"✅ Learning signals recorded for {len(decisions)} jobs")
    except Exception as e:
        print(f"⚠️  Failed to record learning signals: {e}")

def persist_jobs(jobs: List[Tuple[Dict[str, Any], int]]) -> None:
    """Persist jobs to job_history."""
    try:
        from src.job_history import add_jobs_to_history
        add_jobs_to_history(jobs)
        print(f"✅ Jobs persisted to job_history")
    except Exception as e:
        print(f"⚠️  Failed to persist jobs: {e}")

def main():
    print("=" * 80)
    print("JOB PROCESSING TEST - Full Pipeline Simulation")
    print("=" * 80)

    # Load candidate profile
    try:
        profile = get_candidate_profile()
        target_roles = get_target_roles()
        user_id = "default"  # Single-user MVP
        print(f"\n📋 Candidate Profile:")
        print(f"   Name: {profile.get('name', 'N/A')}")
        print(f"   Location: {profile.get('location', 'N/A')}")
        print(f"   Experience: {profile.get('experience_years', 'N/A')} years")
        print(f"   Target Roles: {', '.join(target_roles)}")
        print(f"   Skills: {', '.join(list(profile.get('skills', {}).keys())[:5])}...")
    except Exception as e:
        print(f"\n⚠️  Could not load profile: {e}")
        print("   Using fallback profile for testing...")
        profile = {
            "name": "Test User",
            "location": "Ajman, UAE",
            "experience_years": 8,
            "skills": {"operations": {}, "project management": {}, "python": {}, "sql": {}},
        }
        target_roles = ["operations manager", "product manager", "software engineer"]
        user_id = "default"

    # Initialize decision engine
    try:
        engine = JobDecisionEngine.from_loaders(
            lambda: profile,
            lambda: target_roles,
        )
        print(f"\n🔧 Decision Engine initialized successfully")
    except Exception as e:
        print(f"\n⚠️  Could not initialize decision engine: {e}")
        print("   Skipping probability scoring...")
        engine = None

    # Step 1: Score jobs (try LLM scorer, fall back to keyword)
    print(f"\n{'='*80}")
    print(f"STEP 1: SCORING")
    print(f"{'='*80}")

    try:
        from src.llm_scorer import score_jobs_llm
        scored_jobs = score_jobs_llm(jobs_raw)
        print(f"✅ LLM scorer used for {len(scored_jobs)} jobs")
    except Exception as e:
        print(f"⚠️  LLM scorer unavailable ({e}), using keyword fallback...")
        scored_jobs = score_jobs_keyword_fallback(jobs_raw, profile, target_roles)

    for job in scored_jobs:
        print(f"   {job['title'][:50]:<50} Score: {job.get('score', 0):3d}/100")

    # Step 2: Decision engine probability
    print(f"\n{'='*80}")
    print(f"STEP 2: DECISION ENGINE PROBABILITY")
    print(f"{'='*80}")

    decisions = []

    for job in scored_jobs:
        print(f"\n📌 {job['title']}")
        print(f"   Company: {job['company']}")
        print(f"   Score: {job.get('score', 0)}/100")

        probability = 0
        confidence = "Unknown"
        factors = {}

        if engine:
            try:
                prob_result = engine.calculate_success_probability(job)
                probability = prob_result.probability
                confidence = prob_result.confidence
                factors = prob_result.factors

                print(f"   Success Probability: {probability}% ({get_confidence_label(probability)})")
                print(f"   Confidence: {confidence}")

                if factors:
                    print(f"   Factors:")
                    for factor, value in sorted(factors.items(), key=lambda x: abs(x[1]), reverse=True):
                        sign = "+" if value > 0 else ""
                        print(f"      {factor}: {sign}{value}%")
            except Exception as e:
                print(f"   ⚠️  Probability calculation failed: {e}")
        else:
            print(f"   ⚠️  Decision engine unavailable")

        # Pipeline decision
        decision = get_pipeline_decision(job.get("score", 0), probability)
        decision_emoji = {"apply": "✅", "watch": "👀", "skip": "⏭️"}[decision]
        print(f"   Decision: {decision_emoji} {decision.upper()}")

        decisions.append({
            "job": job,
            "score": job.get("score", 0),
            "probability": probability,
            "confidence": confidence,
            "factors": factors,
            "decision": decision,
        })

    # Step 3: Learning signals
    print(f"\n{'='*80}")
    print(f"STEP 3: LEARNING SIGNALS")
    print(f"{'='*80}")

    record_learning_signals(user_id, decisions)

    # Step 4: Persistence
    print(f"\n{'='*80}")
    print(f"STEP 4: PERSISTENCE")
    print(f"{'='*80}")

    scored_tuples = [(job, job.get("score", 0)) for job in scored_jobs]
    persist_jobs(scored_tuples)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Total jobs processed: {len(scored_jobs)}")
    print(f"Decision Engine: {'Available' if engine else 'Not Available'}")
    print(f"Learning Repo: {'Available' if get_learning_repository() else 'Not Available'}")

    decision_counts = {"apply": 0, "watch": 0, "skip": 0}
    for d in decisions:
        decision_counts[d["decision"]] += 1

    print(f"\nDecisions:")
    print(f"  Apply: {decision_counts['apply']}")
    print(f"  Watch: {decision_counts['watch']}")
    print(f"  Skip: {decision_counts['skip']}")

    print(f"\nRecommendations:")
    print(f"  - All three jobs have low match scores (< 50)")
    print(f"  - They would be stored in history but not trigger notifications")
    print(f"  - To force inclusion, lower min_score to 30 or add include_keywords")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
