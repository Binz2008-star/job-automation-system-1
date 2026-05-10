"""
src/repositories/settings_repo.py
DB I/O for the settings table. Callers receive plain dicts — no SQL here above this layer.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.db import get_db_connection

logger = logging.getLogger(__name__)

def read(user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Load settings row from Postgres.
    When ``user_id`` is provided, returns that user's row; otherwise falls back
    to the legacy "default" row for the single-user pipeline.
    Returns None if the row doesn't exist or DB is unavailable.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT include_keywords, exclude_keywords, min_score,
                          max_daily_applies, telegram_chat_id
                   FROM settings WHERE user_id = %s""",
                (user_id or "default",),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "include_keywords": list(row[0] or []),
            "exclude_keywords": list(row[1] or []),
            "min_score": row[2],
            "max_daily_applies": row[3],
            "telegram_chat_id": row[4] or "",
        }
    except Exception:
        logger.exception("settings_repo_read_failed")
        return None
    finally:
        conn.close()


def upsert(data: Dict[str, Any], user_id: Optional[str] = None) -> None:
    """Insert or update the settings row for the given user."""
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings (
                    user_id, include_keywords, exclude_keywords,
                    min_score, max_daily_applies, telegram_chat_id, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    include_keywords  = COALESCE(EXCLUDED.include_keywords,  settings.include_keywords),
                    exclude_keywords  = COALESCE(EXCLUDED.exclude_keywords,  settings.exclude_keywords),
                    min_score         = COALESCE(EXCLUDED.min_score,         settings.min_score),
                    max_daily_applies = COALESCE(EXCLUDED.max_daily_applies, settings.max_daily_applies),
                    telegram_chat_id  = COALESCE(EXCLUDED.telegram_chat_id,  settings.telegram_chat_id),
                    updated_at        = NOW()
                """,
                (
                    user_id or "default",
                    data.get("include_keywords"),
                    data.get("exclude_keywords"),
                    data.get("min_score"),
                    data.get("max_daily_applies"),
                    data.get("telegram_chat_id"),
                ),
            )
    except Exception:
        logger.exception("settings_repo_upsert_failed")
    finally:
        conn.close()
