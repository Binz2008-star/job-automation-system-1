"""
src/repositories/audit_repo.py
Action audit log persistence and idempotency checking.

Two storage paths:
  1. DB preferred: writes to action_audit_log table.
  2. In-memory fallback: TTL-based dict when DB is unavailable.

Idempotency scope: "apply" actions only.
  Same action_id submitted twice within _DEDUP_TTL_S → second call is rejected.
  action_id is deterministic (SHA-256 of type:link), so clicking Apply twice
  on the same job always produces the same id.
"""
from __future__ import annotations

import logging
import time
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from src.db import get_db_connection, is_db_available
from src.models.action_log import ActionLog

logger = logging.getLogger(__name__)

_UTC = timezone.utc

# ── In-process idempotency cache (TTL-based) ──────────────────────────────────
# action_id -> (unix_timestamp_of_execution, result_status)
_DEDUP_CACHE: Dict[str, Tuple[float, str]] = {}
_DEDUP_TTL_S = 3600   # 1 hour
_DEDUP_LOCK  = threading.Lock()

# Only these action types are subject to idempotency enforcement
IDEMPOTENT_ACTION_TYPES = frozenset({"apply", "skip", "save", "block"})


# ── Idempotency check ─────────────────────────────────────────────────────────

def is_duplicate(action_id: str) -> bool:
    """
    Return True if this action_id was already executed within the TTL window.
    Checks DB first, then in-memory cache.
    """
    if is_db_available():
        return _db_check_duplicate(action_id)
    return _mem_check_duplicate(action_id)


def _db_check_duplicate(action_id: str) -> bool:
    conn = get_db_connection()
    if not conn:
        return _mem_check_duplicate(action_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM action_audit_log
                WHERE action_id = %s
                  AND result_status IN ('success', 'duplicate')
                  AND timestamp > NOW() - INTERVAL '1 hour'
                LIMIT 1
                """,
                (action_id,),
            )
            return cur.fetchone() is not None
    except Exception:
        logger.exception("audit_repo_dedup_check_failed action_id=%s", action_id)
        return _mem_check_duplicate(action_id)
    finally:
        conn.close()


def _mem_check_duplicate(action_id: str) -> bool:
    now = time.monotonic()
    with _DEDUP_LOCK:
        entry = _DEDUP_CACHE.get(action_id)
        if entry is None:
            return False
        ts, status = entry
        if now - ts > _DEDUP_TTL_S:
            del _DEDUP_CACHE[action_id]
            return False
        return status in ("success", "duplicate")


# ── Audit log write ───────────────────────────────────────────────────────────

def log_action(log: ActionLog) -> None:
    """
    Persist one action execution record.
    Also seeds the in-memory dedup cache for processes without DB access.
    """
    _mem_seed(log)

    if is_db_available():
        _db_write(log)
    else:
        logger.info(
            "action_audit action_id=%s type=%s user=%s status=%s duration_ms=%d failure=%r",
            log.get("action_id", ""),
            log.get("action_type", ""),
            log.get("user_email", ""),
            log.get("result_status", ""),
            log.get("duration_ms", 0),
            log.get("failure_reason"),
        )


def _db_write(log: ActionLog) -> None:
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO action_audit_log (
                    action_id, action_type, user_email,
                    job_id, job_title, job_company,
                    timestamp, result_status, result_message,
                    duration_ms, failure_reason
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    log.get("action_id", ""),
                    log.get("action_type", ""),
                    log.get("user_email", ""),
                    log.get("job_id"),
                    log.get("job_title"),
                    log.get("job_company"),
                    log.get("timestamp", datetime.now(_UTC).isoformat()),
                    log.get("result_status", ""),
                    log.get("result_message", ""),
                    log.get("duration_ms", 0),
                    log.get("failure_reason"),
                ),
            )
        logger.info(
            "action_audit action_id=%s type=%s user=%s status=%s duration_ms=%d",
            log.get("action_id", ""),
            log.get("action_type", ""),
            log.get("user_email", ""),
            log.get("result_status", ""),
            log.get("duration_ms", 0),
        )
    except Exception:
        logger.exception("audit_repo_write_failed action_id=%s", log.get("action_id"))
    finally:
        conn.close()


def _mem_seed(log: ActionLog) -> None:
    action_id = log.get("action_id", "")
    if not action_id:
        return
    with _DEDUP_LOCK:
        _DEDUP_CACHE[action_id] = (time.monotonic(), log.get("result_status", ""))


# ── Recent log query (for inspection / tests) ─────────────────────────────────

def get_recent(limit: int = 20) -> list:
    """Return recent audit log entries from DB, or [] when DB is unavailable."""
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT action_id, action_type, user_email, job_title,
                       timestamp, result_status, duration_ms, failure_reason
                FROM action_audit_log
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            {
                "action_id": r[0], "action_type": r[1], "user_email": r[2],
                "job_title": r[3], "timestamp": r[4].isoformat() if r[4] else None,
                "result_status": r[5], "duration_ms": r[6], "failure_reason": r[7],
            }
            for r in rows
        ]
    except Exception:
        logger.exception("audit_repo_get_recent_failed")
        return []
    finally:
        conn.close()
