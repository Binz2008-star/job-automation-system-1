"""
src/agent/tools/messaging_tools.py
Tools for job-related messaging, explanations, and reminders.
All imports are deferred to avoid eager loading of heavy deps.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict

from src.schemas.agent import ToolExecutionResult

logger = logging.getLogger(__name__)


def _timed(tool_name: str, success: bool, payload, elapsed: int) -> ToolExecutionResult:
    if success:
        data = payload if isinstance(payload, dict) else {"result": payload}
        logger.info("tool_executed name=%s duration_ms=%d success=True", tool_name, elapsed)
        return ToolExecutionResult(success=True, tool_name=tool_name, data=data, execution_time_ms=elapsed)
    logger.warning("tool_executed name=%s duration_ms=%d success=False error=%r", tool_name, elapsed, str(payload))
    return ToolExecutionResult(success=False, tool_name=tool_name, error=str(payload), execution_time_ms=elapsed)


def draft_message(job: Dict[str, Any]) -> ToolExecutionResult:
    """Generate a tailored application message for a job."""
    start = time.monotonic()
    try:
        from src.message_generator import generate_message
        text = generate_message(job)
        return _timed("draft_message", True, {"draft": text, "title": job.get("title", "")},
                      int((time.monotonic() - start) * 1000))
    except Exception as exc:
        return _timed("draft_message", False, exc, int((time.monotonic() - start) * 1000))


def explain_match(job: Dict[str, Any]) -> ToolExecutionResult:
    """Return Rico's explanation for why this job was recommended."""
    start = time.monotonic()
    try:
        reason = (
            job.get("profile_explanation")
            or job.get("match_reason")
            or job.get("rico_explanation")
            or "This job matched your current role, location, and search preferences."
        )
        return _timed("explain_match", True,
                      {"explanation": str(reason), "title": job.get("title", "")},
                      int((time.monotonic() - start) * 1000))
    except Exception as exc:
        return _timed("explain_match", False, exc, int((time.monotonic() - start) * 1000))


def set_reminder(job: Dict[str, Any]) -> ToolExecutionResult:
    """Set a 2-day reminder for a job by updating its application status."""
    start = time.monotonic()
    try:
        from src.applications import update_application_status
        reminder_date = (datetime.now() + timedelta(days=2)).date().isoformat()
        update_application_status(job, "saved", notes=f"Reminder requested for {reminder_date}")
        return _timed("set_reminder", True,
                      {"reminder_date": reminder_date, "title": job.get("title", "")},
                      int((time.monotonic() - start) * 1000))
    except Exception as exc:
        return _timed("set_reminder", False, exc, int((time.monotonic() - start) * 1000))
