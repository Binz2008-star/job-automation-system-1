"""
src/repositories/users_repo.py
DB-backed user lookup and creation.
Falls back gracefully when the DB is unavailable — callers handle None.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class User:
    id: int
    email: str
    password_hash: str
    role: str           # "admin" | "user"
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]


def get_user_by_email(email: str) -> Optional[User]:
    """Return the User row for this email, or None if not found / DB unavailable."""
    from src.db import get_db_connection, is_db_available
    if not is_db_available():
        return None
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, password_hash, role, is_active, created_at, last_login_at
                FROM users
                WHERE email = %s AND is_active = TRUE
                LIMIT 1
                """,
                (email.strip().lower(),),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return User(
                id=row[0],
                email=row[1],
                password_hash=row[2],
                role=row[3],
                is_active=row[4],
                created_at=row[5],
                last_login_at=row[6],
            )
    except Exception:
        logger.exception("users_repo_get_failed email=%s", email)
        return None
    finally:
        conn.close()


def create_user(email: str, password_hash: str, role: str = "user") -> Optional[User]:
    """Insert a new user row. Returns the created User or None on failure."""
    from src.db import get_db_connection, is_db_available
    if not is_db_available():
        return None
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES (%s, %s, %s)
                RETURNING id, email, password_hash, role, is_active, created_at, last_login_at
                """,
                (email.strip().lower(), password_hash, role),
            )
            row = cur.fetchone()
            conn.commit()
            return User(
                id=row[0],
                email=row[1],
                password_hash=row[2],
                role=row[3],
                is_active=row[4],
                created_at=row[5],
                last_login_at=row[6],
            )
    except Exception:
        logger.exception("users_repo_create_failed email=%s", email)
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        conn.close()


def update_password(email: str, new_hash: str) -> bool:
    """Update password_hash for the given email. Returns True on success."""
    from src.db import get_db_connection, is_db_available
    if not is_db_available():
        return False
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE email = %s AND is_active = TRUE",
                (new_hash, email.strip().lower()),
            )
            updated = cur.rowcount
        conn.commit()
        return updated > 0
    except Exception:
        logger.exception("users_repo_update_password_failed email=%s", email)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def update_last_login(user_id: int) -> None:
    """Update last_login_at for the given user (best-effort, non-blocking)."""
    from src.db import get_db_connection, is_db_available
    if not is_db_available():
        return
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login_at = %s WHERE id = %s",
                (datetime.now(timezone.utc), user_id),
            )
        conn.commit()
    except Exception:
        logger.exception("users_repo_update_last_login_failed user_id=%s", user_id)
    finally:
        conn.close()


def list_active_users() -> List[User]:
    """Return all active users.  Falls back to [] when DB is unavailable.

    This is the source-of-truth for the multi-user daily scheduler.
    Phase-1 scheduler support: returns [] when DB is unavailable.
    """
    from src.db import get_db_connection, is_db_available
    if not is_db_available():
        return []
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, password_hash, role, is_active, created_at, last_login_at
                FROM users
                WHERE is_active = TRUE
                ORDER BY id
                """,
            )
            rows = cur.fetchall()
        return [
            User(
                id=row[0],
                email=row[1],
                password_hash=row[2],
                role=row[3],
                is_active=row[4],
                created_at=row[5],
                last_login_at=row[6],
            )
            for row in rows
        ]
    except Exception:
        logger.exception("users_repo_list_active_failed")
        return []
    finally:
        conn.close()
