"""
src/agent/tools/stats_tools.py
Tools that surface application statistics.
"""
from __future__ import annotations

import logging
import time

from src.schemas.agent import ToolExecutionResult

logger = logging.getLogger(__name__)


def get_application_stats() -> ToolExecutionResult:
    """Return aggregate application statistics from the tracker."""
    start = time.monotonic()
    try:
        from src.repositories.applications_repo import get_stats
        data = get_stats()
        elapsed = int((time.monotonic() - start) * 1000)
        logger.info("tool_executed name=get_application_stats duration_ms=%d success=True", elapsed)
        return ToolExecutionResult(
            success=True,
            tool_name="get_application_stats",
            data=data,
            execution_time_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.warning("tool_executed name=get_application_stats success=False error=%r", str(exc))
        return ToolExecutionResult(
            success=False,
            tool_name="get_application_stats",
            error=str(exc),
            execution_time_ms=elapsed,
        )
