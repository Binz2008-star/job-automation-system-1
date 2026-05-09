"""
src/repositories/pipeline_repo.py
DB I/O for the pipeline_runs table.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.db import get_db_connection

logger = logging.getLogger(__name__)


def insert_run() -> Optional[int]:
    """Insert a new 'running' row; return its integer id."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pipeline_runs (started_at, status) VALUES (NOW(), 'running') RETURNING id",
            )
            row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        logger.exception("pipeline_repo_insert_failed")
        return None
    finally:
        conn.close()


def update_run(run_id: int, status: str, error: Optional[str] = None) -> None:
    """Mark a run as done or failed."""
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE pipeline_runs
                   SET status = %s, finished_at = NOW(), error = %s
                   WHERE id = %s""",
                (status, error, run_id),
            )
    except Exception:
        logger.exception("pipeline_repo_update_failed run_id=%s", run_id)
    finally:
        conn.close()


def get_latest() -> Optional[Dict[str, Any]]:
    """Return the most recent pipeline_runs row, or None."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, started_at, finished_at, status, jobs_found, error
                   FROM pipeline_runs
                   ORDER BY started_at DESC
                   LIMIT 1""",
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "run_id": row[0],
            "started_at": row[1].isoformat() if row[1] else None,
            "finished_at": row[2].isoformat() if row[2] else None,
            "status": row[3],
            "jobs_found": row[4] or 0,
            "error": row[5],
        }
    except Exception:
        logger.exception("pipeline_repo_get_latest_failed")
        return None
    finally:
        conn.close()
