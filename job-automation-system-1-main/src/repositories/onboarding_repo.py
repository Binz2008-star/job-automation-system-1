"""src/repositories/onboarding_repo.py
Persist and retrieve Rico onboarding state from the DB.
Falls back gracefully when the DB is unavailable — callers handle None.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from src.models.onboarding import (
    ONBOARDING_COMPLETED,
    ONBOARDING_IN_PROGRESS,
    ONBOARDING_PENDING,
    OnboardingState,
)

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rico_onboarding_states (
    user_id      TEXT        PRIMARY KEY,
    status       TEXT        NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending', 'in_progress', 'completed')),
    completed_at TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def _get_conn():
    from src.db import get_db_connection, is_db_available
    if not is_db_available():
        return None
    return get_db_connection()


def _ensure_table(conn) -> None:
    """Create table on first use — idempotent."""
    try:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
        conn.commit()
    except Exception:
        logger.exception("onboarding_repo: failed to ensure table")
        try:
            conn.rollback()
        except Exception:
            pass


def get_onboarding_state(user_id: str) -> Optional[OnboardingState]:
    """Return the persisted OnboardingState, or None if DB unavailable / row absent."""
    conn = _get_conn()
    if not conn:
        return None
    try:
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, completed_at, updated_at FROM rico_onboarding_states WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return OnboardingState(
            user_id=user_id,
            status=row[0],
            completed_at=row[1],
            updated_at=row[2],
        )
    except Exception:
        logger.exception("onboarding_repo: get_failed user_id=%s", user_id)
        return None
    finally:
        conn.close()


def set_onboarding_status(user_id: str, status: str) -> None:
    """Upsert the onboarding status for a user."""
    conn = _get_conn()
    if not conn:
        return
    try:
        _ensure_table(conn)
        now = datetime.now(timezone.utc)
        completed_at = now if status == ONBOARDING_COMPLETED else None
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rico_onboarding_states (user_id, status, completed_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                    SET status       = EXCLUDED.status,
                        completed_at = COALESCE(EXCLUDED.completed_at,
                                                rico_onboarding_states.completed_at),
                        updated_at   = EXCLUDED.updated_at
                """,
                (user_id, status, completed_at, now),
            )
        conn.commit()
    except Exception:
        logger.exception("onboarding_repo: set_status_failed user_id=%s status=%s", user_id, status)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def is_onboarding_complete(user_id: str) -> bool:
    """Return True only if DB confirms this user completed onboarding."""
    state = get_onboarding_state(user_id)
    return state is not None and state.is_complete()


def mark_onboarding_complete(user_id: str) -> None:
    set_onboarding_status(user_id, ONBOARDING_COMPLETED)
