"""
src/services/apply_service.py
Delegates browser-automation apply requests to the correct engine.
Routes call apply_to_job() — never import engine modules directly.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _is_browser_unavailable(exc: Exception) -> bool:
    """Detect Playwright / browser-launch errors that should surface as 'manual_required'."""
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in (
            "playwright install",
            "browser type",
            "chromium",
            "executable",
            "browser not found",
            "executable doesn't exist",
            "browser.launch",
            "failed to launch",
        )
    )


def _clean_apply_error(exc: Exception) -> Dict[str, str]:
    """Return a user-facing message. Log raw technical detail server-side only."""
    if _is_browser_unavailable(exc):
        logger.warning("browser_unavailable: %s", exc)
        return {
            "status": "manual_required",
            "message": "Manual apply required. Browser automation is unavailable for this job.",
        }
    logger.exception("apply_failed")
    return {
        "status": "error",
        "message": "Application failed. Please try again or apply manually.",
    }


def apply_to_job(job: Dict[str, Any]) -> Dict[str, str]:
    """
    Trigger automated application for a job.
    Returns: {"status": str, "message": str, "job_id": str (optional)}
    """
    link = (job.get("link") or "").lower()

    if not link:
        return {"status": "error", "message": "Job is missing a link"}

    if "naukrigulf.com" in link:
        return _apply_naukrigulf(job)

    if "indeed.com" in link:
        return _apply_indeed(job)

    if "linkedin.com" in link:
        return {
            "status": "unsupported",
            "message": "LinkedIn Easy Apply is not enabled in this environment",
        }

    return {
        "status": "unsupported",
        "message": (
            f"No automated apply engine is available for this source. "
            f"Open manually: {job.get('link', '')}"
        ),
    }


def _apply_naukrigulf(job: Dict[str, Any]) -> Dict[str, str]:
    try:
        from src.naukrigulf_apply import run_naukrigulf_apply

        results = run_naukrigulf_apply(jobs=[job], max_applies=1)
        if not results:
            return {"status": "no_result", "message": "Apply engine returned no result"}

        result = results[0]
        return {
            "status": result.status.value,
            "message": result.message or f"Applied to {job.get('title', 'Unknown')}",
            "job_id": result.job_id or "",
        }
    except Exception as exc:
        return _clean_apply_error(exc)


def _apply_indeed(job: Dict[str, Any]) -> Dict[str, str]:
    try:
        from src.indeed_apply import IndeedApplyEngine

        with IndeedApplyEngine() as engine:
            result = engine.apply_one(job)
        return {
            "status": result.status.value,
            "message": result.message,
            "job_id": result.job_id,
        }
    except Exception as exc:
        return _clean_apply_error(exc)
