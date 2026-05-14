"""
src/agent/tools/pipeline_tools.py
Tools for pipeline status and manual triggering.
"""
from __future__ import annotations

import logging
import time

from src.schemas.agent import ToolExecutionResult

logger = logging.getLogger(__name__)


def get_pipeline_status() -> ToolExecutionResult:
    """Return the most recent pipeline run state."""
    start = time.monotonic()
    try:
        from src.services.pipeline_service import get_status
        data = get_status()
        elapsed = int((time.monotonic() - start) * 1000)
        logger.info("tool_executed name=get_pipeline_status duration_ms=%d success=True", elapsed)
        return ToolExecutionResult(
            success=True,
            tool_name="get_pipeline_status",
            data=data,
            execution_time_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.warning("tool_executed name=get_pipeline_status success=False error=%r", str(exc))
        return ToolExecutionResult(
            success=False,
            tool_name="get_pipeline_status",
            error=str(exc),
            execution_time_ms=elapsed,
        )


def trigger_pipeline() -> ToolExecutionResult:
    """Manually trigger the daily pipeline. Returns 'already_running' if busy."""
    start = time.monotonic()
    try:
        from src.services.pipeline_service import trigger
        trigger()
        elapsed = int((time.monotonic() - start) * 1000)
        logger.info("tool_executed name=trigger_pipeline duration_ms=%d success=True", elapsed)
        return ToolExecutionResult(
            success=True,
            tool_name="trigger_pipeline",
            data={"status": "triggered"},
            execution_time_ms=elapsed,
        )
    except RuntimeError as exc:
        # RuntimeError = already running; not a crash
        elapsed = int((time.monotonic() - start) * 1000)
        return ToolExecutionResult(
            success=False,
            tool_name="trigger_pipeline",
            error=str(exc),
            execution_time_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.warning("tool_executed name=trigger_pipeline success=False error=%r", str(exc))
        return ToolExecutionResult(
            success=False,
            tool_name="trigger_pipeline",
            error=str(exc),
            execution_time_ms=elapsed,
        )
