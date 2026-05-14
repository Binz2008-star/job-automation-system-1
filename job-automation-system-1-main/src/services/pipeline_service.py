"""
src/services/pipeline_service.py
Business logic for triggering and tracking pipeline runs.
All DB I/O goes through repositories.pipeline_repo.
All Playwright / browser code stays in src.run_daily — never imported here.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.db import is_db_available
from src.repositories import pipeline_repo

logger = logging.getLogger(__name__)

_UTC = timezone.utc

# In-memory fallback state when DB is unavailable
_mem: Dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "jobs_found": 0,
    "error": None,
}
_mem_lock = threading.Lock()


def get_status() -> Dict[str, Any]:
    """Return the latest pipeline run state (DB preferred, memory fallback)."""
    if is_db_available():
        run = pipeline_repo.get_latest()
        if run:
            return run
    with _mem_lock:
        return dict(_mem)


def trigger() -> None:
    """
    Start the pipeline in a background thread.
    Raises RuntimeError if a run is already in progress.
    """
    if is_db_available():
        run = pipeline_repo.get_latest()
        if run and run.get("status") == "running":
            raise RuntimeError("A pipeline run is already in progress")
        run_id = pipeline_repo.insert_run()
    else:
        with _mem_lock:
            if _mem["status"] == "running":
                raise RuntimeError("A pipeline run is already in progress")
            _mem.update(
                {
                    "status": "running",
                    "started_at": datetime.now(_UTC).isoformat(),
                    "finished_at": None,
                    "error": None,
                }
            )
        run_id = None

    thread = threading.Thread(
        target=_run_bg,
        args=(run_id,),
        daemon=True,
        name="pipeline-trigger",
    )
    thread.start()


def _run_bg(run_id: Optional[int]) -> None:
    """Execute run_pipeline() and record the outcome."""
    try:
        from src.run_daily import run_pipeline
        run_pipeline()

        if run_id is not None:
            pipeline_repo.update_run(run_id, "done")
        else:
            with _mem_lock:
                _mem.update(
                    {"status": "done", "finished_at": datetime.now(_UTC).isoformat()}
                )

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("pipeline_bg_run_failed")
        if run_id is not None:
            pipeline_repo.update_run(run_id, "failed", error_msg)
        else:
            with _mem_lock:
                _mem.update(
                    {
                        "status": "failed",
                        "finished_at": datetime.now(_UTC).isoformat(),
                        "error": error_msg,
                    }
                )
