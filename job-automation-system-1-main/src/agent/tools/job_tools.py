"""
src/agent/tools/job_tools.py
Tools that operate on job data.
Each function calls services — never repos or DB directly.
All service imports are deferred to avoid eager loading of heavy dependencies.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from src.schemas.agent import ToolExecutionResult

logger = logging.getLogger(__name__)


def _timed(tool_name: str, success: bool, data_or_error, elapsed: int) -> ToolExecutionResult:
    """Build a ToolExecutionResult, normalising non-dict return values to dicts."""
    if success:
        if isinstance(data_or_error, dict):
            data = data_or_error
        elif data_or_error is None:
            data = {}
        else:
            data = {"result": data_or_error}
        logger.info("tool_executed name=%s duration_ms=%d success=True", tool_name, elapsed)
        return ToolExecutionResult(success=True, tool_name=tool_name, data=data, execution_time_ms=elapsed)
    else:
        logger.warning("tool_executed name=%s duration_ms=%d success=False error=%r", tool_name, elapsed, str(data_or_error))
        return ToolExecutionResult(success=False, tool_name=tool_name, error=str(data_or_error), execution_time_ms=elapsed)


def search_jobs(
    min_score: int = 0,
    page: int = 1,
    limit: int = 20,
    source: Optional[str] = None,
) -> ToolExecutionResult:
    """Return paginated jobs filtered by minimum score."""
    from src.services.jobs_service import list_jobs
    start = time.monotonic()
    try:
        data = list_jobs(page=page, limit=limit, min_score=min_score, source=source)
        return _timed("search_jobs", True, data, int((time.monotonic() - start) * 1000))
    except Exception as exc:
        return _timed("search_jobs", False, exc, int((time.monotonic() - start) * 1000))


def get_ranked_jobs(
    min_score: int = 60,
    limit: int = 10,
) -> ToolExecutionResult:
    """Return top-scored jobs — the default 'show me best jobs' response."""
    from src.services.jobs_service import list_jobs
    start = time.monotonic()
    try:
        data = list_jobs(page=1, limit=limit, min_score=min_score)
        return _timed("get_ranked_jobs", True, data, int((time.monotonic() - start) * 1000))
    except Exception as exc:
        return _timed("get_ranked_jobs", False, exc, int((time.monotonic() - start) * 1000))


def apply_job(job: Dict[str, Any]) -> ToolExecutionResult:
    """Trigger automated application for a single job."""
    if not job.get("link"):
        return ToolExecutionResult(
            success=False,
            tool_name="apply_job",
            error="Job payload is missing required 'link' field",
        )
    from src.services.apply_service import apply_to_job
    start = time.monotonic()
    try:
        data = apply_to_job(job)
        return _timed("apply_job", True, data, int((time.monotonic() - start) * 1000))
    except Exception as exc:
        return _timed("apply_job", False, exc, int((time.monotonic() - start) * 1000))


def skip_job(job: Dict[str, Any]) -> ToolExecutionResult:
    """Mark a job as skipped so it won't resurface."""
    from src.services.jobs_service import skip_job as _svc_skip
    start = time.monotonic()
    try:
        skipped = _svc_skip(job)
        elapsed = int((time.monotonic() - start) * 1000)
        data = {"skipped": bool(skipped), "title": job.get("title", "Unknown")}
        return _timed("skip_job", True, data, elapsed)
    except Exception as exc:
        return _timed("skip_job", False, exc, int((time.monotonic() - start) * 1000))


def save_job(job: Dict[str, Any]) -> ToolExecutionResult:
    """Save a job without applying — marks as 'saved' in the tracker."""
    from src.applications import mark_applied
    start = time.monotonic()
    try:
        saved = mark_applied(job, "saved", "Saved via agent")
        elapsed = int((time.monotonic() - start) * 1000)
        data = {"saved": bool(saved), "title": job.get("title", "Unknown")}
        return _timed("save_job", True, data, elapsed)
    except Exception as exc:
        return _timed("save_job", False, exc, int((time.monotonic() - start) * 1000))


def block_company(job: Dict[str, Any]) -> ToolExecutionResult:
    """Block all future results from this company."""
    from src.services.jobs_service import block_company as _svc_block
    start = time.monotonic()
    try:
        company = _svc_block(job)
        elapsed = int((time.monotonic() - start) * 1000)
        return _timed("block_company", True, {"company": company}, elapsed)
    except ValueError as exc:
        return _timed("block_company", False, exc, int((time.monotonic() - start) * 1000))
    except Exception as exc:
        return _timed("block_company", False, exc, int((time.monotonic() - start) * 1000))
