"""
src/run_daily.py
Daily job search pipeline.

Execution order:
  1. Init DB
  2. Fetch + filter jobs
  3. Score + persist
  4. Notify (email + Telegram)
  5. Apply assistant for top matches
  6. Feedback loop (non-blocking, against full history)
  7. Dashboard regeneration

Run:
    python -m src.run_daily
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("run_daily")

from src.job_sources import get_jobs
from src.scoring import score_job, get_profile_explanation
from src.llm_scorer import score_jobs_llm
from src.message_generator import generate_message
from src.filter import filter_new_jobs
from src.notifier import send_email, format_jobs_email
from src.telegram_bot import send_telegram_message, format_telegram_jobs
from src.job_history import add_jobs_to_history, load_job_history
from src.apply_assistant import run_apply_assistant
from src.db import init_db, save_job, is_db_available, get_top_jobs
from src.profile import get_candidate_profile, get_target_roles
from src.applications import get_applied_jobs
from src.decision_engine import JobDecisionEngine
from src.feedback_loop import FeedbackLoopOrchestrator, CycleResult
from src.dashboard import build_dashboard

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DASHBOARD_FILE = BASE_DIR / "dashboard.html"

# 23h: prevents double-runs on the same calendar day; still allows a
# manual retry after a failure without waiting a full 24h.
_FEEDBACK_COOLDOWN = timedelta(hours=23)


def _init_db() -> None:
    if not is_db_available():
        logger.info("db_unavailable json_fallback_active")
        return
    logger.info("db_initializing")
    if init_db():
        logger.info("db_ready")
    else:
        logger.warning("db_init_failed json_fallback_active")


def _build_orchestrator() -> Optional[FeedbackLoopOrchestrator]:
    """
    Build engine + orchestrator once per run.
    Returns None on failure — pipeline continues without the feedback loop.
    """
    try:
        decision_engine = JobDecisionEngine.from_loaders(
            get_candidate_profile,  # function reference, not its result
            get_target_roles,
        )
        orchestrator = FeedbackLoopOrchestrator.build(
            decision_engine=decision_engine,
            state_dir=DATA_DIR,           # consistent with rest of system
            cooldown=_FEEDBACK_COOLDOWN,
        )
        logger.info(
            f"orchestrator_ready "
            f"last_run={orchestrator.cycle_state.last_run_at} "
            f"adjustments_v={orchestrator.cycle_state.last_adjustments_version}"
        )
        return orchestrator
    except Exception:
        logger.exception("orchestrator_init_failed feedback_loop_disabled")
        return None


def _fetch_and_score() -> Tuple[
    List[Tuple[Dict[str, Any], int]],
    List[Tuple[Dict[str, Any], int]],
]:
    """Returns (all_scored, high_quality_matches). High quality = score >= 65."""
    jobs = get_jobs()
    jobs = filter_new_jobs(jobs)
    logger.info(f"jobs_fetched count={len(jobs)}")

    # LLM scoring with keyword fallback
    logger.info(f"scoring_starting jobs_count={len(jobs)}")
    jobs = score_jobs_llm(jobs)

    all_scored: List[Tuple[Dict[str, Any], int]] = []
    for job in jobs:
        score = job["score"]
        all_scored.append((job, score))
        if is_db_available():
            save_job(job, score)

    matches = sorted(
        [(j, s) for j, s in all_scored if s >= 45],
        key=lambda x: x[1],
        reverse=True,
    )
    logger.info(f"scoring_complete total={len(all_scored)} high_quality={len(matches)}")
    print(f"Scoring complete: {len(all_scored)} jobs scored, {len(matches)} high quality matches")

    # Agent decision making
    from src.job_agent import decide_jobs
    agent_jobs = []
    for job, score in matches:
        job["score"] = score
        agent_jobs.append(job)

    decisions = decide_jobs(agent_jobs, generate_letters=False)
    apply_decisions = [d for d in decisions if d.decision == "apply"]
    watch_decisions = [d for d in decisions if d.decision == "watch"]
    skip_decisions = [d for d in decisions if d.decision == "skip"]

    print(f"Agent decisions: apply={len(apply_decisions)} watch={len(watch_decisions)} skip={len(skip_decisions)}")

    # Use Agent decisions as final output
    apply_jobs = [(d.job, d.final_score) for d in apply_decisions]
    watch_jobs = [(d.job, d.final_score) for d in watch_decisions]

    # NEW: limit applies to top 4 by score (STRICT cap)
    apply_jobs = sorted(apply_jobs, key=lambda x: x[1], reverse=True)
    apply_jobs = apply_jobs[:4]

    # Combine apply and watch jobs
    final_matches = apply_jobs + watch_jobs

    # Filter out already applied jobs — batch check (single file read)
    from src.applications import is_applied_batch, get_job_id
    all_candidate_jobs = [j for j, _ in final_matches] + [j for j, _ in matches]
    applied_map = is_applied_batch(all_candidate_jobs)

    filtered_matches = []
    applied_count = 0

    for job, score in final_matches:
        if applied_map.get(get_job_id(job), False):
            applied_count += 1
            logger.info(f"filtering_applied job={job.get('title', 'unknown')} company={job.get('company', 'unknown')}")
        else:
            filtered_matches.append((job, score))

    # Force minimum output: ensure at least 5 jobs (using cached applied_map)
    if len(filtered_matches) < 5:
        for job, score in matches:
            if not applied_map.get(get_job_id(job), False) and len(filtered_matches) < 5:
                filtered_matches.append((job, score))

    logger.info(f"job_filtering_complete applied_filtered={applied_count} final_jobs={len(filtered_matches)}")
    print(f"Final output: telegram_jobs={len(filtered_matches)} (filtered from {len(final_matches)}, removed {applied_count} applied)")

    return all_scored, filtered_matches


def _persist_history(all_scored: List[Tuple[Dict[str, Any], int]]) -> None:
    try:
        add_jobs_to_history(all_scored)
        logger.info(f"history_saved count={len(all_scored)}")
    except Exception:
        logger.exception("history_save_failed")


def _notify(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    try:
        subject = "Job Hunting Daily Report" if matches else "No New Jobs Today"
        if send_email(subject, format_jobs_email(matches)):
            logger.info("email_sent")
        else:
            logger.warning("email_failed")
    except Exception:
        logger.exception("email_error")

    try:
        if send_telegram_message(format_telegram_jobs(matches)):
            logger.info("telegram_sent")
        else:
            logger.warning("telegram_failed")
    except Exception:
        logger.exception("telegram_error")


def _apply_assistant(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    if not matches:
        logger.info("apply_assistant_skipped no_matches")
        return
    try:
        # Log apply decisions even when automated application is disabled
        from src.applications import mark_applied, is_applied

        apply_decisions = [job for job, score in matches if score >= 75]
        logger.info(f"apply_assistant_logging apply_decisions={len(apply_decisions)}")

        for job in apply_decisions:
            if not is_applied(job):
                # Mark as "decision_made" status to track AI decisions without actual application
                mark_applied(job, status="decision_made")
                logger.info(f"apply_decision_logged title={job.get('title', 'unknown')} company={job.get('company', 'unknown')}")

        # # run_apply_assistant(matches)  # disabled - requires interactive input
        logger.info(f"apply_assistant_done candidates={len(matches)}")
    except Exception:
        logger.exception("apply_assistant_error")


def _auto_apply_linkedin(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    """Auto-apply to LinkedIn jobs via Easy Apply (DISABLED - use NaukriGulf instead)."""
    if not matches:
        logger.info("auto_apply_linkedin_disabled no_matches")
        return

    logger.info("auto_apply_linkedin_disabled use_naukrigulf_instead")


def _auto_apply_naukrigulf(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    """Auto-apply to NaukriGulf jobs via persistent browser automation."""
    try:
        from src.naukrigulf_apply import run_naukrigulf_apply, NGApplyStatus

        logger.info("naukrigulf_apply_starting direct_search")
        # Use direct search mode (jobs=None) to let NaukriGulf engine find jobs
        results = run_naukrigulf_apply(jobs=None, max_applies=2)

        success_count = sum(1 for r in results if r.status == NGApplyStatus.SUCCESS)
        dry_count     = sum(1 for r in results if r.status == NGApplyStatus.DRY_RUN)
        logger.info(
            f"naukrigulf_apply_complete success={success_count} "
            f"dry_run={dry_count} total={len(results)}"
        )

    except Exception:
        logger.exception("naukrigulf_apply_error")


def _run_feedback_loop(
    orchestrator: Optional[FeedbackLoopOrchestrator],
) -> Optional[CycleResult]:
    """
    Learn from full job history + all tracked applications.

    Loads full history — not just today's new jobs. Today's 10-20 new jobs
    have no application matches yet; learning against them always exits
    with "insufficient data".
    """
    if orchestrator is None:
        return None

    if not orchestrator.is_due():
        logger.info(
            f"feedback_loop_not_due last_run={orchestrator.cycle_state.last_run_at}"
        )
        return None

    logger.info("feedback_loop_starting")

    def _load_jobs() -> List[Dict[str, Any]]:
        if is_db_available():
            return get_top_jobs(500)
        return load_job_history()

    result = orchestrator.run_cycle_sync(
        jobs_loader=_load_jobs,
        apps_loader=get_applied_jobs,
    )

    if result.status == "success":
        logger.info(
            f"feedback_loop_success "
            f"matched={result.matched_pairs} "
            f"adjustments_v={result.adjustments_version} "
            f"insights={result.insights_count} "
            f"duration_s={result.duration_seconds:.2f}"
        )
    elif result.status == "skipped":
        logger.info(f"feedback_loop_skipped reason={result.skipped_reason}")
    else:
        logger.error(f"feedback_loop_failed error={result.error}")

    return result


def _sync_gmail() -> None:
    try:
        from src.gmail_importer import run_import
        report = run_import(dry_run=False)
        logger.info(
            f"gmail_sync_complete "
            f"classified={report.emails_classified} "
            f"updated={report.updates_applied} "
            f"queued={report.queued_for_review}"
        )
    except Exception:
        logger.exception("gmail_sync_failed")


def _regenerate_dashboard(
    orchestrator: Optional[FeedbackLoopOrchestrator],
) -> None:
    try:
        html = build_dashboard(orchestrator=orchestrator)
        DASHBOARD_FILE.write_text(html, encoding="utf-8")
        logger.info(f"dashboard_written path={DASHBOARD_FILE}")
    except Exception:
        logger.exception("dashboard_generation_failed")


def run_pipeline() -> None:
    started = datetime.now()
    logger.info(f"pipeline_start at={started.isoformat()}")

    _init_db()
    orchestrator = _build_orchestrator()
    all_scored, matches = _fetch_and_score()
    _persist_history(all_scored)
    _notify(matches)
    _apply_assistant(matches)
    _auto_apply_naukrigulf(matches)
    _sync_gmail()
    _run_feedback_loop(orchestrator)
    _regenerate_dashboard(orchestrator)

    elapsed = (datetime.now() - started).total_seconds()
    logger.info(f"pipeline_complete duration_s={elapsed:.1f}")


def main() -> None:
    run_pipeline()


if __name__ == "__main__":
    main()
