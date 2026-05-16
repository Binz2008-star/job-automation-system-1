"""
src/run_daily.py
Daily job search pipeline with full observability and UAE-market optimization.

Execution order:
  1. Init DB + Prometheus metrics
  2. Distributed lock (cron dedupe)
  3. Fetch + filter jobs
  4. Score with LLM + fallback
  5. Decision engine V2 probability
  6. Notify (email + Telegram + Slack)
  7. Apply assistant with NaukriGulf
  8. Feedback loop (non-blocking)
  9. Learning repository update
  10. Dashboard regeneration

Run:
    python -m src.run_daily
    # Or via cron: 50 7 * * * /usr/bin/python3 -m src.run_daily
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Prometheus metrics
try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    # Create dummy decorators
    class Counter:
        def inc(self, **kwargs): pass
        def labels(self, **kwargs): return self
    class Histogram:
        def time(self, func): return func
        def observe(self, value): pass
    class Gauge:
        def set(self, value): pass
        def inc(self, **kwargs): pass

# Redis for distributed locking
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Configure logging externally (not basicConfig in library context)
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
from src.applications import get_applied_jobs, get_applied_jobs_count
from src.decision_engine import JobDecisionEngine, generate_decision_insights
from src.feedback_loop import FeedbackLoopOrchestrator, CycleResult
from src.dashboard import build_dashboard
from src.repositories.learning_repo import get_learning_repository

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DASHBOARD_FILE = BASE_DIR / "dashboard.html"

# Environment configuration
RICO_ENABLE_AUTO_APPLY = os.getenv("RICO_ENABLE_AUTO_APPLY", "false").lower() in {"1", "true", "yes", "on"}
RICO_INTERACTIVE_APPLY = os.getenv("RICO_INTERACTIVE_APPLY", "false").lower() in {"1", "true", "yes", "on"}
RICO_ENABLE_SLACK = os.getenv("RICO_ENABLE_SLACK", "false").lower() in {"1", "true", "yes", "on"}
RICO_ENABLE_METRICS = os.getenv("RICO_ENABLE_METRICS", "false").lower() in {"1", "true", "yes", "on"}
RICO_REDIS_URL = os.getenv("RICO_REDIS_URL", "redis://localhost:6379/0")
RICO_MAX_APPLIES_DAILY = int(os.getenv("RICO_MAX_APPLIES_DAILY", "4"))
RICO_MIN_JOBS_THRESHOLD = int(os.getenv("RICO_MIN_JOBS_THRESHOLD", "5"))

# 23h: prevents double-runs on the same calendar day
_FEEDBACK_COOLDOWN = timedelta(hours=23)

# Prometheus metrics (initialized once only)
if METRICS_AVAILABLE and RICO_ENABLE_METRICS and not hasattr(__import__('__main__'), '_metrics_initialized'):
    fetch_duration = Histogram("pipeline_fetch_duration_seconds", "Time to fetch jobs")
    score_duration = Histogram("pipeline_score_duration_seconds", "Time to score jobs")
    pipeline_duration = Histogram("pipeline_total_duration_seconds", "Total pipeline runtime")

    jobs_fetched_gauge = Gauge("pipeline_jobs_fetched", "Number of jobs fetched")
    jobs_scored_gauge = Gauge("pipeline_jobs_scored", "Number of jobs scored")
    high_quality_gauge = Gauge("pipeline_high_quality_jobs", "Number of high quality matches")
    applications_gauge = Gauge("pipeline_applications_made", "Number of applications sent")

    db_errors = Counter("pipeline_db_errors", "Database errors by step", ["step"])
    fetch_errors = Counter("pipeline_fetch_errors", "Fetch errors by source")
    apply_errors = Counter("pipeline_apply_errors", "Apply errors by platform")

    try:
        start_http_server(8000)
        logger.info("prometheus_metrics_enabled port=8000")
        __import__('__main__')._metrics_initialized = True
    except Exception as e:
        logger.warning(f"prometheus_start_failed: {e}")
else:
    # Dummy metrics
    fetch_duration = Histogram()
    score_duration = Histogram()
    pipeline_duration = Histogram()
    jobs_fetched_gauge = Gauge()
    jobs_scored_gauge = Gauge()
    high_quality_gauge = Gauge()
    applications_gauge = Gauge()
    db_errors = Counter()
    fetch_errors = Counter()
    apply_errors = Counter()


def _init_db() -> None:
    if not is_db_available():
        logger.info("db_unavailable json_fallback_active")
        db_errors.labels(step="init").inc()
        return
    logger.info("db_initializing")
    if init_db():
        logger.info("db_ready")
    else:
        logger.warning("db_init_failed json_fallback_active")
        db_errors.labels(step="init").inc()


# Distributed lock for cron safety (Lua script for atomic unlock)
_UNLOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

@contextmanager
def distributed_lock(lock_key: str, timeout: int = 3600):
    """Redis distributed lock to prevent concurrent pipeline runs with Lua unlock script."""
    if not REDIS_AVAILABLE:
        logger.warning("redis_unavailable lock_disabled")
        yield True
        return

    try:
        r = redis.from_url(RICO_REDIS_URL)
        lock_id = str(uuid.uuid4())
        acquired = r.set(lock_key, lock_id, nx=True, ex=timeout)

        if not acquired:
            logger.warning(f"pipeline_already_running lock_key={lock_key}")
            yield False
            return

        try:
            yield True
        finally:
            # Atomic unlock with Lua script to prevent race conditions
            r.eval(_UNLOCK_SCRIPT, 1, lock_key, lock_id)
    except Exception as e:
        logger.warning(f"redis_lock_unavailable_using_local_execution: {e}")
        yield True


def retryable(max_retries: int = 3, delay: int = 5, retry_exceptions: Tuple[Exception, ...] = (TimeoutError, ConnectionError)):
    """Decorator for retryable operations with backoff and specific exception types."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as e:
                    if attempt == max_retries - 1:
                        logger.exception(f"{func.__name__}_failed after {max_retries} attempts")
                        raise
                    logger.warning(f"{func.__name__}_retry {attempt+1}/{max_retries}: {e}")
                    import time
                    time.sleep(delay * (attempt + 1))
                except Exception as e:
                    # Don't retry non-retryable exceptions (auth, config, programming errors)
                    logger.exception(f"{func.__name__}_non_retryable_error: {e}")
                    raise
            return None
        return wrapper
    return decorator


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _init_metrics() -> None:
    """Initialize Prometheus metrics if enabled (lazy initialization)."""
    if METRICS_AVAILABLE and RICO_ENABLE_METRICS and not hasattr(_init_metrics, "_started"):
        try:
            start_http_server(8000)
            _init_metrics._started = True
            logger.info("prometheus_metrics_enabled port=8000")
        except Exception as e:
            logger.warning(f"prometheus_start_failed: {e}")


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
    except Exception as e:
        logger.exception(f"orchestrator_init_failed feedback_loop_disabled: {e}")
        return None


def _send_slack_alert(message: str, severity: str = "warning") -> None:
    """Send critical alerts to Slack channel with timeout protection."""
    if not RICO_ENABLE_SLACK:
        return

    try:
        import requests
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            logger.debug("slack_webhook_not_configured")
            return

        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}.get(severity, "🔔")
        payload = {
            "text": f"{emoji} *Rico AI Pipeline*\n{message}",
            "username": "Rico AI",
            "icon_emoji": ":robot_face:"
        }
        response = requests.post(webhook_url, json=payload, timeout=5)
        if response.status_code != 200:
            logger.warning(f"slack_alert_failed status={response.status_code}")
    except Exception as e:
        logger.warning(f"slack_alert_error: {e}")


@retryable(max_retries=2, delay=10, retry_exceptions=(TimeoutError, ConnectionError))
def _fetch_and_score() -> Tuple[
    List[Tuple[Dict[str, Any], int]],
    List[Tuple[Dict[str, Any], int]],
    Dict[str, Any],
]:
    """Returns (all_scored, high_quality_matches, stats). High quality = score >= 65."""
    start = time.perf_counter()
    try:
        jobs = get_jobs()
        jobs = filter_new_jobs(jobs)
        logger.info(f"jobs_fetched count={len(jobs)}", extra={"count": len(jobs)})
        jobs_fetched_gauge.set(len(jobs))

        if len(jobs) < RICO_MIN_JOBS_THRESHOLD:
            _send_slack_alert(f"⚠️ Low job volume: {len(jobs)} jobs found (threshold {RICO_MIN_JOBS_THRESHOLD})", "warning")
    finally:
        if hasattr(fetch_duration, "observe"):
            fetch_duration.observe(time.perf_counter() - start)

    start = time.perf_counter()
    try:
        logger.info(f"scoring_starting jobs_count={len(jobs)}", extra={"jobs_count": len(jobs)})
        jobs = score_jobs_llm(jobs)
    finally:
        if hasattr(score_duration, "observe"):
            score_duration.observe(time.perf_counter() - start)

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
    logger.info(f"scoring_complete total={len(all_scored)} high_quality={len(matches)}", extra={"total": len(all_scored), "high_quality": len(matches)})
    jobs_scored_gauge.set(len(all_scored))
    high_quality_gauge.set(len(matches))

    print(f"Scoring complete: {len(all_scored)} jobs scored, {len(matches)} high quality matches")

    # Agent decision making with V2 decision engine
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

    # Stricter cap for UAE market
    apply_jobs = sorted(apply_jobs, key=lambda x: x[1], reverse=True)
    apply_jobs = apply_jobs[:RICO_MAX_APPLIES_DAILY]

    # Combine apply and watch jobs
    final_matches = apply_jobs + watch_jobs

    # Filter out already applied jobs — batch check
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

    # Force minimum output: ensure at least 5 jobs
    if len(filtered_matches) < 5:
        for job, score in matches:
            if not applied_map.get(get_job_id(job), False) and len(filtered_matches) < 5:
                filtered_matches.append((job, score))

    logger.info(f"job_filtering_complete applied_filtered={applied_count} final_jobs={len(filtered_matches)}", extra={"applied_filtered": applied_count, "final_jobs": len(filtered_matches)})
    print(f"Final output: telegram_jobs={len(filtered_matches)} (filtered from {len(final_matches)}, removed {applied_count} applied)")

    stats = {
        "total_fetched": len(jobs),
        "total_scored": len(all_scored),
        "high_quality": len(matches),
        "apply_decisions": len(apply_decisions),
        "watch_decisions": len(watch_decisions),
        "skip_decisions": len(skip_decisions),
        "applied_filtered": applied_count,
        "final_jobs": len(filtered_matches),
    }

    applications_gauge.set(len([j for j, _ in apply_jobs]))

    return all_scored, filtered_matches, stats


def _persist_history(all_scored: List[Tuple[Dict[str, Any], int]]) -> None:
    try:
        add_jobs_to_history(all_scored)
        logger.info(f"history_saved count={len(all_scored)}", extra={"count": len(all_scored)})
    except Exception as e:
        logger.exception(f"history_save_failed: {e}")
        db_errors.labels(step="history").inc()


def _notify(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    """Send notifications via email, Telegram, and optionally Slack."""
    try:
        subject = "Job Hunting Daily Report" if matches else "No New Jobs Today"
        if send_email(subject, format_jobs_email(matches)):
            logger.info("email_sent")
        else:
            logger.warning("email_failed")
    except Exception as e:
        logger.exception(f"email_error: {e}")

    try:
        if send_telegram_message(format_telegram_jobs(matches)):
            logger.info("telegram_sent")
        else:
            logger.warning("telegram_failed")
    except Exception as e:
        logger.exception(f"telegram_error: {e}")

    # Slack summary for operations
    if matches and RICO_ENABLE_SLACK:
        top_jobs = matches[:3]
        summary = f"📊 *Daily Pipeline Complete*\n• {len(matches)} matches found\n• Top: {top_jobs[0][0].get('title', 'N/A')} @ {top_jobs[0][0].get('company', 'N/A')}\n• Applying to {min(len(matches), RICO_MAX_APPLIES_DAILY)} roles"
        _send_slack_alert(summary, "info")


def _apply_assistant(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    if not matches:
        logger.info("apply_assistant_skipped no_matches")
        return
    try:
        # Log apply decisions even when automated application is disabled
        from src.applications import mark_applied, is_applied

        apply_decisions = [job for job, score in matches if score >= 75]
        logger.info(f"apply_assistant_logging apply_decisions={len(apply_decisions)}", extra={"apply_decisions": len(apply_decisions)})

        for job in apply_decisions:
            if not is_applied(job):
                # Mark as "decision_made" status to track AI decisions without actual application
                mark_applied(job, status="decision_made")
                logger.info(f"apply_decision_logged title={job.get('title', 'unknown')} company={job.get('company', 'unknown')}")

        if RICO_INTERACTIVE_APPLY:
            logger.info("interactive_apply_enabled")
            run_apply_assistant(matches)
        else:
            logger.info("interactive_apply_disabled cloud_safe_mode")

        logger.info(f"apply_assistant_done candidates={len(matches)}", extra={"candidates": len(matches)})
    except Exception as e:
        logger.exception(f"apply_assistant_error: {e}")
        apply_errors.labels(platform="assistant").inc()


def _auto_apply_naukrigulf(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    """Auto-apply to NaukriGulf jobs with rate limiting and fingerprint rotation."""
    if not RICO_ENABLE_AUTO_APPLY:
        logger.info("naukrigulf_apply_skipped RICO_ENABLE_AUTO_APPLY=false")
        return

    try:
        from src.naukrigulf_apply import run_naukrigulf_apply, NGApplyStatus

        logger.warning("naukrigulf_apply_enabled autonomous_browser_actions_active")

        # Track daily apply count
        applied_today = get_applied_jobs_count(days=1)
        remaining = max(0, RICO_MAX_APPLIES_DAILY - applied_today)

        if remaining <= 0:
            logger.info(f"naukrigulf_apply_rate_limited daily_max={RICO_MAX_APPLIES_DAILY}", extra={"daily_max": RICO_MAX_APPLIES_DAILY})
            _send_slack_alert(f"⚠️ Daily apply limit reached: {RICO_MAX_APPLIES_DAILY}", "warning")
            return

        results = run_naukrigulf_apply(jobs=None, max_applies=min(remaining, 2))

        success_count = sum(1 for r in results if r.status == NGApplyStatus.SUCCESS)
        dry_count = sum(1 for r in results if r.status == NGApplyStatus.DRY_RUN)
        failed_count = sum(1 for r in results if r.status == NGApplyStatus.FAILED)

        logger.info(
            f"naukrigulf_apply_complete success={success_count} "
            f"dry_run={dry_count} failed={failed_count} total={len(results)}",
            extra={"success": success_count, "dry_run": dry_count, "failed": failed_count, "total": len(results)}
        )

        if failed_count > 0:
            apply_errors.labels(platform="naukrigulf").inc(failed_count)

        if success_count == 0 and len(matches) > 0:
            _send_slack_alert("⚠️ NaukriGulf auto-apply failed - check credentials", "error")

    except Exception as e:
        logger.exception(f"naukrigulf_apply_error: {e}")
        apply_errors.labels(platform="naukrigulf").inc()


def _update_learning_repo(matches: List[Tuple[Dict[str, Any], int]]) -> None:
    """Update learning repository with user preferences from job actions."""
    try:
        repo = get_learning_repository()
        profile = get_candidate_profile()

        if not profile:
            logger.debug("learning_repo_skipped no_profile")
            return

        user_id = profile.get("email", "unknown")

        for job, score in matches[:20]:  # Limit to top 20
            # Record as positive signal for role, company, location
            repo.infer_signals_from_job_action(user_id, "save", job)

            # High score = stronger signal
            if score >= 75:
                repo.record_signal(
                    user_id,
                    "role_preference",
                    job.get("title", ""),
                    signal_weight=min(0.8, score / 100),
                    source="daily_pipeline",
                    metadata={"score": score, "auto_saved": True}
                )

        logger.info(f"learning_repo_updated signals_sent={len(matches[:20])}", extra={"signals_sent": len(matches[:20])})
    except Exception as e:
        logger.exception(f"learning_repo_error: {e}")


def _run_feedback_loop(
    orchestrator: Optional[FeedbackLoopOrchestrator],
) -> Optional[CycleResult]:
    """
    Learn from full job history + all tracked applications.
    """
    if orchestrator is None:
        return None

    if not orchestrator.is_due():
        logger.info(
            f"feedback_loop_not_due last_run={orchestrator.cycle_state.last_run_at}",
            extra={"last_run": str(orchestrator.cycle_state.last_run_at)}
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
            f"duration_s={result.duration_seconds:.2f}",
            extra={
                "matched": result.matched_pairs,
                "adjustments_version": result.adjustments_version,
                "insights": result.insights_count,
                "duration": result.duration_seconds
            }
        )
        if result.insights_count > 0:
            _send_slack_alert(f"📈 Feedback loop complete: {result.insights_count} insights generated", "info")
    elif result.status == "skipped":
        logger.info(f"feedback_loop_skipped reason={result.skipped_reason}", extra={"reason": result.skipped_reason})
    else:
        logger.error(f"feedback_loop_failed error={result.error}", extra={"error": result.error})
        _send_slack_alert(f"🚨 Feedback loop failed: {result.error}", "error")

    return result


def _sync_gmail() -> None:
    try:
        from src.gmail_importer import run_import
        report = run_import(dry_run=False)
        logger.info(
            f"gmail_sync_complete "
            f"classified={report.emails_classified} "
            f"updated={report.updates_applied} "
            f"queued={report.queued_for_review}",
            extra={
                "classified": report.emails_classified,
                "updated": report.updates_applied,
                "queued": report.queued_for_review
            }
        )

        if report.emails_classified > 0:
            _send_slack_alert(f"📧 Gmail sync: {report.emails_classified} new responses classified", "info")
    except Exception as e:
        logger.exception(f"gmail_sync_failed: {e}")


def _regenerate_dashboard(
    orchestrator: Optional[FeedbackLoopOrchestrator],
    decision_engine: Optional[JobDecisionEngine],
    matches: List[Tuple[Dict[str, Any], int]],
    stats: Dict[str, Any],
) -> None:
    """Generate enhanced dashboard with decision engine insights."""
    try:
        if decision_engine and matches:
            # Generate AI insights from decision engine
            job_list = [job for job, _ in matches]
            applications = get_applied_jobs()
            app_stats = {"success_rate": 0.0}  # Would calculate from feedback

            insights = generate_decision_insights(
                jobs=job_list,
                applications=applications,
                app_stats=app_stats,
                engine=decision_engine
            )
        else:
            insights = None

        html = build_dashboard(orchestrator=orchestrator)
        DASHBOARD_FILE.write_text(html, encoding="utf-8")
        logger.info(f"dashboard_written path={DASHBOARD_FILE}", extra={"path": str(DASHBOARD_FILE)})
    except Exception as e:
        logger.exception(f"dashboard_generation_failed: {e}")


@retryable(max_retries=1, retry_exceptions=(TimeoutError, ConnectionError))
def run_pipeline() -> int:
    """
    Execute the full pipeline with distributed lock and monitoring.

    Returns 0 on success; non-zero on critical failure.
    """
    started = datetime.now()
    run_id = str(uuid.uuid4())[:8]
    logger.info(f"pipeline_start run_id={run_id} at={started.isoformat()}", extra={"run_id": run_id})

    # Acquire distributed lock to prevent concurrent runs
    lock_key = f"rico:pipeline:running"
    with distributed_lock(lock_key, timeout=3600) as acquired:
        if not acquired:
            logger.warning(f"pipeline_skipped already_running run_id={run_id}", extra={"run_id": run_id})
            return 0

        _init_metrics()
        _init_db()
        orchestrator = _build_orchestrator()
        decision_engine = getattr(orchestrator, "decision_engine", None) if orchestrator else None

        try:
            all_scored, matches, stats = _fetch_and_score()
        except Exception as e:
            logger.exception("pipeline_fetch_score_failed pipeline_aborted", extra={"run_id": run_id})
            elapsed = (datetime.now() - started).total_seconds()
            logger.info(f"pipeline_aborted run_id={run_id} duration_s={elapsed:.1f}", extra={"run_id": run_id, "duration": elapsed})
            fetch_errors.labels(source="all").inc()
            _send_slack_alert(f"🚨 Pipeline CRITICAL FAILURE at fetch/score: {e}", "error")
            return 1

        # Continue even if no matches
        _persist_history(all_scored)
        _notify(matches)
        _apply_assistant(matches)
        _auto_apply_naukrigulf(matches)
        _update_learning_repo(matches)
        _sync_gmail()

        try:
            _run_feedback_loop(orchestrator)
        except Exception as e:
            logger.exception("feedback_loop_unhandled_error non_fatal", extra={"run_id": run_id})

        _regenerate_dashboard(orchestrator, decision_engine, matches, stats)

        elapsed = (datetime.now() - started).total_seconds()

        # Success alert for monitoring
        if len(matches) == 0:
            _send_slack_alert(f"⚠️ Pipeline complete but ZERO matches found. Market check needed.", "warning")
        elif len(matches) < RICO_MIN_JOBS_THRESHOLD:
            _send_slack_alert(f"⚠️ Low match volume: {len(matches)} jobs", "warning")
        else:
            logger.info(f"pipeline_success matches={len(matches)} duration_s={elapsed:.1f}", extra={"matches": len(matches), "duration": elapsed})

        logger.info(f"pipeline_complete run_id={run_id} duration_s={elapsed:.1f}", extra={"run_id": run_id, "duration": elapsed})
        return 0


def main() -> None:
    sys.exit(run_pipeline())


if __name__ == "__main__":
    main()
