"""Background task functions for Rico.

Tasks are plain Python functions so they can run directly without Redis, or be
enqueued through RQ when REDIS_URL is configured.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List


def run_daily_pipeline_task() -> Dict[str, Any]:
    from src.run_daily import run_pipeline

    started = datetime.utcnow()
    run_pipeline()
    return {
        "task": "run_daily_pipeline",
        "status": "completed",
        "started_at": started.isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
    }


def send_weekly_report_task() -> Dict[str, Any]:
    from src.weekly_report import send_weekly_report

    ok = send_weekly_report()
    return {
        "task": "send_weekly_report",
        "status": "completed" if ok else "failed",
        "completed_at": datetime.utcnow().isoformat(),
    }


def check_followups_task(days_after_apply: int = 14) -> Dict[str, Any]:
    from src.applications import get_applied_jobs
    from src.telegram_bot import send_telegram_message

    now = datetime.utcnow()
    due: List[Dict[str, Any]] = []

    for app in get_applied_jobs():
        if not isinstance(app, dict):
            continue
        status = app.get("status", "")
        if status not in {"applied", "saved", "decision_made"}:
            continue

        raw_date = app.get("date_applied") or app.get("created_at")
        if not raw_date:
            continue

        try:
            applied_at = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue

        if now - applied_at >= timedelta(days=days_after_apply):
            due.append(app)

    if due:
        lines = ["<b>Rico follow-up reminders</b>", ""]
        for app in due[:10]:
            title = app.get("title", "Role")
            company = app.get("company", "Company")
            lines.append(f"• {title} — {company}")
        send_telegram_message("\n".join(lines))

    return {
        "task": "check_followups",
        "status": "completed",
        "due_count": len(due),
        "completed_at": now.isoformat(),
    }


def adapt_rankings_task(user_id: str = "default") -> Dict[str, Any]:
    from src.rico_memory import RicoMemoryStore

    store = RicoMemoryStore()
    signals = store.load_learning_signals(user_id)

    action_counts: Dict[str, int] = {}
    for signal in signals:
        action = signal.get("action", "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1

    store.add_memory(
        user_id=user_id,
        memory_type="system",
        content=f"Ranking adaptation snapshot: {action_counts}",
        source="worker.adapt_rankings",
        confidence=0.65,
        metadata={"action_counts": action_counts},
    )

    return {
        "task": "adapt_rankings",
        "status": "completed",
        "user_id": user_id,
        "action_counts": action_counts,
        "completed_at": datetime.utcnow().isoformat(),
    }


def detect_opportunities_task(user_id: str = "default") -> Dict[str, Any]:
    from src.job_history import load_job_history
    from src.rico_memory import RicoMemoryStore
    from src.telegram_bot import send_telegram_message

    store = RicoMemoryStore()
    history = load_job_history()
    recent_high = [j for j in history if isinstance(j, dict) and int(j.get("score", 0) or 0) >= 75]
    recent_high = sorted(recent_high, key=lambda j: int(j.get("score", 0) or 0), reverse=True)[:5]

    if recent_high:
        store.add_memory(
            user_id=user_id,
            memory_type="outcome",
            content=f"Rico noticed {len(recent_high)} strong recent opportunities above score 75.",
            source="worker.detect_opportunities",
            confidence=0.8,
            metadata={"count": len(recent_high)},
        )

        lines = ["<b>Rico noticed strong opportunities</b>", ""]
        for job in recent_high:
            lines.append(f"• {job.get('title', 'Role')} — {job.get('company', 'Company')} | Score {job.get('score', '-')}")
        send_telegram_message("\n".join(lines))

    return {
        "task": "detect_opportunities",
        "status": "completed",
        "user_id": user_id,
        "opportunity_count": len(recent_high),
        "completed_at": datetime.utcnow().isoformat(),
    }


def process_telegram_action_task(update: Dict[str, Any]) -> Dict[str, Any]:
    from src.rico_telegram_webhook import process_telegram_update

    result = process_telegram_update(update)
    return {
        "task": "process_telegram_action",
        "status": "completed",
        "result": result,
        "completed_at": datetime.utcnow().isoformat(),
    }
