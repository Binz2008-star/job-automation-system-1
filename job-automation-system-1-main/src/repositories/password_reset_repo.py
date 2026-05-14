"""
src/repositories/password_reset_repo.py
Token storage for the password-reset flow.

Only the SHA-256 hash of the raw token is persisted — plaintext never touches the DB.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)
_UTC = timezone.utc
_TOKEN_TTL_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_reset_token(email: str) -> str:
    """
    Generate a secure reset token, store its hash, return the plaintext token.
    Raises RuntimeError if the DB is unavailable.
    """
    from src.db import get_db_connection
    token      = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    expires_at = datetime.now(_UTC) + timedelta(minutes=_TOKEN_TTL_MINUTES)

    conn = get_db_connection()
    if not conn:
        raise RuntimeError("DB unavailable — cannot create password reset token")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO password_reset_tokens (user_email, token_hash, expires_at)
                VALUES (%s, %s, %s)
                """,
                (email.strip().lower(), token_hash, expires_at),
            )
        conn.commit()
    except Exception:
        logger.exception("password_reset_repo_create_failed email=%s", email)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    return token


def consume_reset_token(token: str) -> Optional[str]:
    """
    Validate the token and mark it used in a single round-trip.
    Returns the associated email on success, None if invalid / expired / already used.
    """
    from src.db import get_db_connection
    token_hash = _hash_token(token)
    now        = datetime.now(_UTC)

    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_email, expires_at, used_at
                FROM password_reset_tokens
                WHERE token_hash = %s
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            row_id, email, expires_at, used_at = row
            if used_at is not None:
                return None  # already consumed
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=_UTC)
            if expires_at < now:
                return None  # expired

            cur.execute(
                "UPDATE password_reset_tokens SET used_at = %s WHERE id = %s",
                (now, row_id),
            )
        conn.commit()
        return email
    except Exception:
        logger.exception("password_reset_repo_consume_failed")
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        conn.close()
