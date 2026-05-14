"""
src/apply_assistant.py
Human-in-the-loop apply assistant with decision engine integration.

Features:
- Interactive mode only (RICO_INTERACTIVE_APPLY=1) - no-ops otherwise
- Decision engine V2 probability scoring
- Learning repository recording of apply/skip decisions
- Optional control server API for remote apply
- Browser automation with session isolation
- Dry-run preview mode (RICO_APPLY_DRY_RUN=1)
- UAE job board support (NaukriGulf, LinkedIn, Indeed)

Security: All functions are no-ops unless RICO_INTERACTIVE_APPLY=1 is set.
In cloud/CI/Docker/cron environments this variable must not be set.
"""
from __future__ import annotations

import json
import logging
import os
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Environment checks
RICO_INTERACTIVE_APPLY = os.getenv("RICO_INTERACTIVE_APPLY", "").strip().lower() in {"1", "true", "yes", "on"}
RICO_APPLY_DRY_RUN = os.getenv("RICO_APPLY_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}
RICO_CONTROL_SERVER_URL = os.getenv("RICO_CONTROL_SERVER_URL", "http://localhost:8000")
RICO_CONTROL_SERVER_API_KEY = os.getenv("CONTROL_SERVER_API_KEY", "")

# Cache for confirmation decisions
CONFIRMATION_LOG = Path(os.getenv("RICO_CONFIRMATION_LOG", "data/apply_decisions.json"))
CONFIRMATION_LOG.parent.mkdir(parents=True, exist_ok=True)

_UTC = timezone.utc

# Schema version for audit log
AUDIT_SCHEMA_VERSION = "1.0"

# Decision engine cache
_decision_engine_cache: Optional[Any] = None


def _atomic_write_json(file_path: Path, data: Any) -> None:
    """Write JSON file atomically to prevent partial writes/corruption."""
    tmp_path = file_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.replace(file_path)
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise e


def _log_decision(job: Dict[str, Any], decision: str, probability: Optional[float] = None) -> None:
    """Log apply/skip decision to persistent JSON for audit with atomic writes."""
    try:
        log_entry = {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "timestamp": datetime.now(_UTC).isoformat(),
            "job_title": job.get("title"),
            "company": job.get("company"),
            "link": job.get("link"),
            "decision": decision,
            "probability": probability,
        }

        existing = []
        if CONFIRMATION_LOG.exists():
            existing = json.loads(CONFIRMATION_LOG.read_text())

        existing.append(log_entry)
        # Keep last 500 decisions
        existing = existing[-500:]
        _atomic_write_json(CONFIRMATION_LOG, existing)
    except Exception as e:
        logger.warning(f"Failed to log decision: {e}")


def _get_decision_engine():
    """Lazy load decision engine with caching to avoid repeated reconstruction."""
    global _decision_engine_cache
    if _decision_engine_cache is not None:
        return _decision_engine_cache

    try:
        from src.decision_engine import JobDecisionEngine
        from src.profile import get_candidate_profile, get_target_roles

        engine = JobDecisionEngine.from_loaders(
            get_candidate_profile,
            get_target_roles,
        )
        _decision_engine_cache = engine
        return engine
    except Exception as e:
        logger.warning(f"Decision engine unavailable: {e}")
        return None


def _record_learning_signal(user_id: str, job: Dict[str, Any], action: str, weight: float) -> None:
    """Record learning signal for user preference."""
    try:
        from src.repositories.learning_repo import get_learning_repository

        repo = get_learning_repository()
        repo.record_signal(
            canonical_user_id=user_id,
            signal_type="role_preference" if action == "apply" else "feedback",
            signal_value=job.get("title", ""),
            signal_weight=weight,
            source="apply_assistant",
            metadata={
                "action": action,
                "company": job.get("company"),
                "location": job.get("location"),
            }
        )
        logger.debug(f"Learning signal recorded: {action} weight={weight}")
    except Exception as e:
        logger.warning(f"Failed to record learning signal: {e}")


def _call_control_server_apply(job: Dict[str, Any]) -> Tuple[bool, str]:
    """Attempt remote apply via control server API."""
    if not RICO_CONTROL_SERVER_API_KEY:
        return False, "Control server API key not configured"

    try:
        import requests

        response = requests.post(
            f"{RICO_CONTROL_SERVER_URL}/apply-one",
            json={"job": job},
            headers={"X-API-Key": RICO_CONTROL_SERVER_API_KEY},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return True, data.get("message", "Applied via control server")
            else:
                return False, data.get("message", "Apply failed")
        else:
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, f"Control server error: {e}"


def open_job_links(
    top_jobs: List[Tuple[Dict[str, Any], int]],
    use_decision_engine: bool = True,
    user_id: Optional[str] = None,
) -> None:
    """
    Open top job links in browser and collect apply confirmations (local only).

    Args:
        top_jobs: List of (job, score) tuples
        use_decision_engine: Use decision engine V2 for probability scoring
        user_id: User ID for learning repository (optional)
    """
    if not RICO_INTERACTIVE_APPLY:
        logger.info("open_job_links_skipped interactive_mode_disabled")
        return
    if not top_jobs:
        print("No jobs to apply for.")
        return

    from src.message_generator import generate_message
    from src.applications import is_applied, mark_applied, filter_unapplied_jobs, get_application_stats

    unapplied_jobs = filter_unapplied_jobs(top_jobs)
    if not unapplied_jobs:
        stats = get_application_stats()
        print(f"✅ All top jobs already applied. Stats: {stats['total_applied']} applied.")
        return

    # Initialize decision engine if requested
    engine = _get_decision_engine() if use_decision_engine else None

    print(f"\n{'='*60}")
    print(f"🎯 APPLY ASSISTANT - Top {len(unapplied_jobs)} Unapplied Jobs")
    if RICO_APPLY_DRY_RUN:
        print("⚠️  DRY RUN MODE - No actual applications will be submitted")
    print(f"{'='*60}")

    for i, (job, score) in enumerate(unapplied_jobs[:5], 1):
        title = job.get("title", "N/A")
        company = job.get("company", "N/A")
        location = job.get("location", "N/A")
        link = job.get("link", "")

        # Get probability from decision engine
        probability = None
        if engine:
            try:
                prob_result = engine.calculate_success_probability(job)
                probability = prob_result.probability
                confidence = prob_result.confidence
                factors = prob_result.factors
            except Exception as e:
                logger.warning(f"Probability calculation failed: {e}")
                confidence = "Unknown"
                factors = {}
        else:
            confidence = "N/A"
            factors = {}

        print(f"\n{'─'*60}")
        print(f"📌 JOB #{i}: {title}")
        print(f"   Company: {company}")
        print(f"   Location: {location}")
        print(f"   Match Score: {score}")
        if probability:
            print(f"   Success Probability: {probability}% ({confidence})")
            if factors:
                top_factor = max(factors.items(), key=lambda x: x[1]) if factors else None
                if top_factor:
                    print(f"   Key Factor: {top_factor[0]} +{top_factor[1]}%")

        # Generate application message
        app_message = generate_message(job, probability=probability)
        print(f"\n📝 Application Message:\n{'-'*40}\n{app_message}\n{'-'*40}")

        if link and link.startswith("http"):
            try:
                print(f"\n🌐 Opening in browser: {link}")
                if not RICO_APPLY_DRY_RUN:
                    webbrowser.open(link)
                    time.sleep(2)  # Give browser time to load
                else:
                    print("   [DRY RUN] Browser open skipped")
            except Exception as exc:
                logger.warning(f"webbrowser_open_failed: {exc}")
                print(f"⚠️  Could not open browser: {exc}")
        else:
            print("⚠️  No valid link for this job")

        if i < len(unapplied_jobs[:5]) and not RICO_APPLY_DRY_RUN:
            response = input("\n✅ Did you apply? (y/n/s for skip permanently): ").lower().strip()
            if response in ("y", "yes"):
                mark_applied(job, status="applied")
                _log_decision(job, "applied", probability)
                if user_id:
                    _record_learning_signal(user_id, job, "apply", weight=0.7)
                print("   ✓ Marked as applied")
            elif response in ("s", "skip"):
                mark_applied(job, status="skipped", notes="Permanently skipped by user")
                _log_decision(job, "skipped", probability)
                if user_id:
                    _record_learning_signal(user_id, job, "skip", weight=-0.3)
                print("   ⏭️  Permanently skipped")
            else:
                print("   ⏭️  Skipped for now (will reappear)")
        elif RICO_APPLY_DRY_RUN:
            print("\n[DRY RUN] Would have prompted for confirmation")
            # In dry run, still log decision
            _log_decision(job, "dry_run", probability)

    stats = get_application_stats()
    print(f"\n{'='*60}")
    print(f"📊 Done. Stats: {stats['total_applied']} applied, {stats.get('interviews_scheduled', 0)} interviews")
    print(f"{'='*60}")


def get_confidence_level(score: int, probability: Optional[float] = None) -> Tuple[str, str]:
    """Get confidence level based on match score and optional probability."""
    if probability:
        # Use probability if available (decision engine)
        if probability >= 80:
            return "Very High", "⭐⭐⭐⭐⭐"
        if probability >= 65:
            return "High", "⭐⭐⭐⭐"
        if probability >= 50:
            return "Medium", "⭐⭐⭐"
        if probability >= 35:
            return "Low", "⭐⭐"
        return "Very Low", "⭐"
    else:
        # Fallback to score
        if score >= 85:
            return "Very High", "⭐⭐⭐⭐⭐"
        if score >= 75:
            return "High", "⭐⭐⭐⭐"
        if score >= 65:
            return "Medium", "⭐⭐⭐"
        if score >= 50:
            return "Low", "⭐⭐"
        return "Very Low", "⭐"


def show_top_jobs_with_confidence(
    matches: List[Tuple[Dict[str, Any], int]],
    use_decision_engine: bool = True,
    max_jobs: int = 3,
) -> List[Tuple[Dict[str, Any], int]]:
    """
    Interactively present top jobs and return the ones user confirms.

    Args:
        matches: List of (job, score) tuples
        use_decision_engine: Use decision engine for probability scoring
        max_jobs: Maximum number of jobs to display

    Returns:
        List of selected (job, score) tuples
    """
    if not RICO_INTERACTIVE_APPLY:
        logger.info("show_top_jobs_skipped interactive_mode_disabled")
        return []
    if not matches:
        print("No jobs to display.")
        return []

    # Initialize decision engine
    engine = _get_decision_engine() if use_decision_engine else None

    # Sort by match score (already sorted, but ensure)
    top_jobs = sorted(matches, key=lambda x: x[1], reverse=True)[:max_jobs]

    print(f"\n{'='*60}")
    print(f"🏆 TOP {len(top_jobs)} RECOMMENDED JOBS")
    print(f"{'='*60}")

    selected = []
    for i, (job, score) in enumerate(top_jobs, 1):
        # Get probability
        probability = None
        if engine:
            try:
                prob_result = engine.calculate_success_probability(job)
                probability = prob_result.probability
            except Exception:
                pass

        confidence, stars = get_confidence_level(score, probability)

        print(f"\n{'─'*60}")
        print(f"🔹 JOB #{i}: {confidence} {stars}")
        print(f"   Title:   {job.get('title', 'N/A')}")
        print(f"   Company: {job.get('company', 'N/A')}")
        print(f"   Location:{job.get('location', 'N/A')}")
        print(f"   Match Score: {score}")
        if probability:
            print(f"   Success Probability: {probability}%")
        print(f"   Why:     {job.get('profile_explanation', 'Relevant experience')}")
        print(f"   Link:    {job.get('link', '')}")

        if not RICO_APPLY_DRY_RUN:
            response = input("\n✅ Apply to this job? (y/n/s for skip permanently): ").lower().strip()
            if response in ("y", "yes"):
                selected.append((job, score))
                print("   ✓ Added to application list")
            elif response in ("s", "skip"):
                # Mark as permanently skipped
                from src.applications import mark_applied
                mark_applied(job, status="skipped", notes="Permanently skipped from interactive selection")
                _log_decision(job, "skipped_interactive", probability)
                print("   ⏭️  Permanently skipped")
            else:
                print("   ⏭️  Skipped for now")
        else:
            print("\n   [DRY RUN] Would have prompted for apply decision")
            selected.append((job, score))  # In dry run, assume selected for testing

    return selected


def run_apply_assistant(
    matches: List[Tuple[Dict[str, Any], int]],
    use_decision_engine: bool = True,
    user_id: Optional[str] = None,
    use_control_server: bool = False,
) -> None:
    """
    Run the interactive apply assistant with decision engine integration.

    Args:
        matches: List of (job, score) tuples
        use_decision_engine: Use decision engine V2 for probability scoring
        user_id: User ID for learning repository
        use_control_server: Attempt remote apply via control server API
    """
    if not RICO_INTERACTIVE_APPLY:
        logger.info("run_apply_assistant_skipped interactive_mode_disabled")
        return
    if not matches:
        print("No high-quality matches to process.")
        return

    from src.applications import filter_unapplied_jobs, mark_applied, get_application_stats
    from src.message_generator import generate_message

    # First, let user select from top jobs with confidence
    selected_jobs = show_top_jobs_with_confidence(matches, use_decision_engine=use_decision_engine, max_jobs=5)
    if not selected_jobs:
        print("No jobs selected for application.")
        return

    # Filter out already applied
    unapplied_jobs = filter_unapplied_jobs(selected_jobs)
    if not unapplied_jobs:
        stats = get_application_stats()
        print(f"✅ All selected jobs already applied. Stats: {stats['total_applied']} applied.")
        return

    print(f"\n{'='*60}")
    print(f"📤 APPLYING TO {len(unapplied_jobs)} SELECTED JOBS")
    if RICO_APPLY_DRY_RUN:
        print("⚠️  DRY RUN MODE - No actual applications will be submitted")
    print(f"{'='*60}")

    for i, (job, score) in enumerate(unapplied_jobs, 1):
        title = job.get("title", "N/A")
        company = job.get("company", "N/A")
        link = job.get("link", "")

        # Get probability again for final display
        probability = None
        if use_decision_engine:
            engine = _get_decision_engine()
            if engine:
                try:
                    prob_result = engine.calculate_success_probability(job)
                    probability = prob_result.probability
                except Exception:
                    pass

        print(f"\n{'─'*60}")
        print(f"📝 APPLICATION #{i}: {title} @ {company}")
        if probability:
            print(f"   Success Probability: {probability}%")
        print(f"   Score: {score}")

        # Generate message
        app_message = generate_message(job, probability=probability)
        print(f"\n✉️  Message:\n{'-'*40}\n{app_message}\n{'-'*40}")

        if link and link.startswith("http"):
            # Determine application method
            if use_control_server and "naukrigulf.com" in link.lower():
                print(f"\n🤖 Attempting auto-apply via control server...")
                success, msg = _call_control_server_apply(job)
                if success:
                    print(f"   ✅ {msg}")
                    mark_applied(job, status="applied", notes="Auto-applied via control server")
                    _log_decision(job, "auto_applied", probability)
                    if user_id:
                        _record_learning_signal(user_id, job, "apply", weight=0.8)
                    continue
                else:
                    print(f"   ⚠️ Auto-apply failed: {msg}")
                    print("   Falling back to manual browser open...")

            # Manual browser open (fallback or by choice)
            try:
                print(f"\n🌐 Opening in browser: {link}")
                if not RICO_APPLY_DRY_RUN:
                    webbrowser.open(link)
                    time.sleep(2)
                else:
                    print("   [DRY RUN] Browser open skipped")
            except Exception as exc:
                logger.warning(f"webbrowser_open_failed: {exc}")
                print(f"⚠️ Could not open browser: {exc}")
        else:
            print("⚠️ No valid link for this job")

        if i < len(unapplied_jobs) and not RICO_APPLY_DRY_RUN:
            response = input("\n✅ Did you apply? (y/n): ").lower().strip()
            if response in ("y", "yes"):
                mark_applied(job, status="applied")
                _log_decision(job, "applied", probability)
                if user_id:
                    _record_learning_signal(user_id, job, "apply", weight=0.7)
                print("   ✓ Marked as applied")
            else:
                print("   ⏭️ Skipped - will reappear in future runs")
        elif RICO_APPLY_DRY_RUN:
            print("\n   [DRY RUN] Would have prompted for confirmation")
            _log_decision(job, "dry_run", probability)

    stats = get_application_stats()
    print(f"\n{'='*60}")
    print(f"🎉 Done. Stats: {stats['total_applied']} applied, {stats.get('interviews_scheduled', 0)} interviews")
    print(f"{'='*60}")


# For backwards compatibility
def get_confidence_level_legacy(score: int) -> Tuple[str, str]:
    """Legacy function without probability support."""
    return get_confidence_level(score, probability=None)


def show_top_jobs_with_confidence_legacy(matches: List[Tuple[Dict[str, Any], int]]) -> List[Tuple[Dict[str, Any], int]]:
    """Legacy function without decision engine."""
    return show_top_jobs_with_confidence(matches, use_decision_engine=False)


def run_apply_assistant_legacy(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    """Legacy function without decision engine."""
    run_apply_assistant(matches, use_decision_engine=False)


if __name__ == "__main__":
    # Test harness (only runs interactively)
    if RICO_INTERACTIVE_APPLY:
        print("Interactive apply assistant ready.")
        print(f"Decision engine: {'enabled' if _get_decision_engine() else 'disabled'}")
        print(f"Dry run mode: {RICO_APPLY_DRY_RUN}")
        print(f"Control server: {'configured' if RICO_CONTROL_SERVER_API_KEY else 'not configured'}")
    else:
        print("Apply assistant disabled. Set RICO_INTERACTIVE_APPLY=1 to enable.")
