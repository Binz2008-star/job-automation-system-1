"""src/services/identity_merge_service.py

Guest → authenticated identity merge service.

Handles migration of profile data when a public (guest) user signs up or logs in,
ensuring CV-extracted skills, experience, and preferences survive authentication.

Design rules:
- Pure merge functions have no DB side effects.
- DB functions are synchronous (psycopg2) matching the existing RicoDB style.
- No raw CV text migration by default.
- No new DB columns.
- Auth scalar values always win over guest values.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json

from src.rico_db import RicoDB

logger = logging.getLogger(__name__)
_UTC = timezone.utc

# Keys allowed to migrate from guest profile → auth profile.
# Scalars: auth wins if already present.
# Lists: merged and deduplicated.
MERGEABLE_PROFILE_KEYS = {
    "email",
    "phone",
    "skills",
    "years_experience",
    "certifications",
    "languages",
    "target_roles",
    "normalized_roles",
    "preferred_cities",
    "industries",
    "cv_filename",
    "cv_status",
    "profile_creation_mode",
    "manual_profile_wizard_disabled",
    "salary_expectation_aed",
    "minimum_salary_aed",
    "deal_breakers",
    "current_role",
    "current_company",
    "visa_status",
    "notice_period",
    "english_level",
    "arabic_level",
    "linkedin_url",
    "portfolio_url",
    "green_flags",
    "red_flags",
}

# Tables confirmed to have a user_id column and be safe to migrate.
CONFIRMED_USER_SCOPED_TABLES = ["rico_saved_searches"]


def is_empty_value(value: Any) -> bool:
    """Return True for None, empty string, empty list, or empty dict."""
    if value is None:
        return True
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        return True
    return False


def normalize_jsonb(data: Any) -> dict[str, Any]:
    """Coerce a JSONB value (dict, JSON string, or None) into a plain dict."""
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def merge_profile_data(
    auth_data: dict[str, Any],
    guest_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge guest profile data into authenticated profile data.

    Rules:
    - Only keys in MERGEABLE_PROFILE_KEYS are considered.
    - Auth scalar values win (not overwritten by guest).
    - Guest fills missing auth values.
    - Lists are merged and deduplicated (guest items appended after auth items).
    - Empty guest values are ignored.
    - Nested dicts are not recursively merged (treated as scalars).

    Returns a new dict; inputs are not mutated.
    """
    result = dict(auth_data)  # shallow copy

    for key, guest_value in guest_data.items():
        if key not in MERGEABLE_PROFILE_KEYS:
            continue
        if is_empty_value(guest_value):
            continue

        auth_value = auth_data.get(key)

        if is_empty_value(auth_value):
            # Auth missing → take guest value
            result[key] = guest_value
        elif isinstance(auth_value, list) and isinstance(guest_value, list):
            # Merge lists, dedupe, preserve auth order then append guest extras
            merged = list(auth_value)
            seen = set(str(v).lower() for v in merged if isinstance(v, str))
            for item in guest_value:
                if isinstance(item, str) and item.lower() not in seen:
                    merged.append(item)
                    seen.add(item.lower())
                elif not isinstance(item, str) and item not in merged:
                    merged.append(item)
            result[key] = merged
        else:
            # Scalar or mismatched types → auth wins, do nothing
            pass

    return result


def _table_exists(cur, table_name: str) -> bool:
    """Check whether a table exists in the public schema."""
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cur.fetchone() is not None


def _column_exists(cur, table_name: str, column_name: str) -> bool:
    """Check whether a column exists on a table."""
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return cur.fetchone() is not None


def _get_db_user_id(cur, external_user_id: str) -> str | None:
    """Resolve external user_id (email or public:web-*) to internal UUID string."""
    cur.execute(
        """
        SELECT id::text FROM rico_users
        WHERE external_user_id = %s OR email = %s OR id::text = %s
        LIMIT 1
        """,
        (external_user_id, external_user_id, external_user_id),
    )
    row = cur.fetchone()
    return row["id"] if row else None


def _read_profile_jsonb(cur, db_user_id: str) -> dict[str, Any]:
    """Fetch profile JSONB for a user by internal UUID."""
    cur.execute(
        "SELECT profile FROM rico_profiles WHERE user_id = %s",
        (db_user_id,),
    )
    row = cur.fetchone()
    return normalize_jsonb(row["profile"] if row else None)


def _write_profile_jsonb(
    cur,
    db_user_id: str,
    data: dict[str, Any],
) -> None:
    """Upsert profile JSONB using the same || merge pattern as RicoDB."""
    cur.execute(
        """
        INSERT INTO rico_profiles (user_id, profile)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            profile = rico_profiles.profile || EXCLUDED.profile,
            updated_at = now()
        """,
        (db_user_id, Json(data)),
    )


def _mark_guest_profile_merged(
    cur,
    guest_db_user_id: str,
    auth_db_user_id: str,
) -> None:
    """Mark the guest profile as merged inside its JSONB data."""
    cur.execute(
        """
        INSERT INTO rico_profiles (user_id, profile)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            profile = rico_profiles.profile || EXCLUDED.profile,
            updated_at = now()
        """,
        (
            guest_db_user_id,
            Json(
                {
                    "profile_status": "merged",
                    "merged_into_user_id": auth_db_user_id,
                    "merged_at": datetime.now(_UTC).isoformat(),
                }
            ),
        ),
    )


def _migrate_user_scoped_rows(
    cur,
    from_db_user_id: str,
    to_db_user_id: str,
) -> None:
    """Migrate rows from confirmed user-scoped tables."""
    for table in CONFIRMED_USER_SCOPED_TABLES:
        if not _table_exists(cur, table):
            logger.debug("merge_skip_table table=%s reason=not_found", table)
            continue
        if not _column_exists(cur, table, "user_id"):
            logger.debug("merge_skip_table table=%s reason=no_user_id_column", table)
            continue
        # Use sql.Literal or psycopg2.sql to safely interpolate the table name
        from psycopg2 import sql as pg_sql

        query = pg_sql.SQL("UPDATE {} SET user_id = %s WHERE user_id = %s").format(
            pg_sql.Identifier(table)
        )
        cur.execute(query, (to_db_user_id, from_db_user_id))
        logger.info(
            "merge_table table=%s from=%s to=%s rows=%s",
            table,
            from_db_user_id,
            to_db_user_id,
            cur.rowcount,
        )


def merge_public_identity_into_auth(
    public_user_id: str,
    auth_user_id: str,
) -> bool:
    """
    Merge a public (guest) identity into an authenticated identity.

    Steps:
    1. Validate inputs (public_user_id must start with "public:").
    2. Resolve both to internal DB UUIDs.
    3. Read guest profile JSONB.
    4. Read auth profile JSONB.
    5. Merge guest data into auth (auth wins scalars, lists deduped).
    6. Write merged profile back to auth.
    7. Mark guest profile as merged.
    8. Migrate confirmed user-scoped rows.

    Returns True on success, False on failure.
    """
    if not public_user_id or not auth_user_id:
        logger.warning("merge_rejected reason=missing_user_id")
        return False
    if not public_user_id.startswith("public:"):
        logger.warning("merge_rejected reason=not_public_source public_user_id=%s", public_user_id)
        return False
    if public_user_id == auth_user_id:
        logger.warning("merge_rejected reason=same_user_id")
        return False

    db = RicoDB()
    if not db.available:
        logger.warning("merge_rejected reason=db_unavailable")
        return False

    conn = db.connect()
    try:
        with conn.cursor() as cur:
            # Resolve external IDs to internal UUIDs
            guest_db_id = _get_db_user_id(cur, public_user_id)
            auth_db_id = _get_db_user_id(cur, auth_user_id)

            if not guest_db_id:
                logger.warning("merge_rejected reason=guest_not_found public_user_id=%s", public_user_id)
                return False
            if not auth_db_id:
                logger.warning("merge_rejected reason=auth_not_found auth_user_id=%s", auth_user_id)
                return False
            if guest_db_id == auth_db_id:
                logger.warning("merge_rejected reason=same_db_id")
                return False

            # Read profiles
            guest_profile = _read_profile_jsonb(cur, guest_db_id)
            auth_profile = _read_profile_jsonb(cur, auth_db_id)

            # Merge
            merged = merge_profile_data(auth_profile, guest_profile)

            # Write merged profile to auth user
            _write_profile_jsonb(cur, auth_db_id, merged)

            # Mark guest as merged
            _mark_guest_profile_merged(cur, guest_db_id, auth_db_id)

            # Migrate confirmed user-scoped tables
            _migrate_user_scoped_rows(cur, guest_db_id, auth_db_id)

        conn.commit()
        logger.info(
            "merge_success public_user_id=%s auth_user_id=%s",
            public_user_id,
            auth_user_id,
        )
        return True

    except Exception:
        conn.rollback()
        logger.exception(
            "merge_failed public_user_id=%s auth_user_id=%s",
            public_user_id,
            auth_user_id,
        )
        return False
    finally:
        conn.close()
