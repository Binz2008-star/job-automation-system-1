"""src/repositories/profile_repo.py
DB-backed user profile, preferences, and saved-search repository.

Read path: DB first (RicoDB.get_user_bundle), falls back to RicoMemoryStore
            when DB is unavailable or user has no DB record yet.
Write path: DB primary; mirrors to JSON store so existing JSON-dependent code
            continues to work during the transition.

Design principles:
- Graceful degradation: DB failures log but don't crash
- Transaction safety: User + profile + settings updates atomic
- Dynamic field extraction: Uses dataclass fields to avoid duplication
- Idempotent operations: Upserts for all write operations
"""
from __future__ import annotations

import logging
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any
from contextlib import contextmanager

from psycopg2.extras import Json

from src.rico_agent import RicoAgentSettings, RicoProfile
from src.rico_db import RicoDB
from src.rico_memory import RicoMemoryStore
from src.services.profile_context_resolver import resolve_profile_context
from src.services.identity_flow_mapper import IdentitySignal

logger = logging.getLogger(__name__)
_UTC = timezone.utc

# Dynamic field extraction from dataclasses
_PROFILE_FIELDS = {f.name for f in fields(RicoProfile)}
_SETTINGS_FIELDS = {f.name for f in fields(RicoAgentSettings)}

# Fields that belong in the main user table (vs profile JSONB)
_USER_TABLE_FIELDS = {
    "external_user_id", "name", "email", "phone", "telegram_username"
}

# Fields that go into profile JSONB
_PROFILE_JSONB_FIELDS = _PROFILE_FIELDS - _USER_TABLE_FIELDS - {"settings"}

# Settings fields that are boolean flags
_BOOLEAN_SETTINGS = {
    "can_reject_unsuitable_jobs",
    "can_learn_from_actions",
    "can_personalize_recommendations",
    "can_generate_cover_letters",
    "can_generate_recruiter_messages",
    "can_prepare_interview_notes",
    "can_send_follow_up_reminders",
    "can_create_weekly_report",
}


@contextmanager
def _db_transaction():
    """Context manager for DB transactions with automatic rollback on error."""
    db = RicoDB()
    if not db.available:
        yield None
        return

    conn = db.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _db() -> RicoDB | None:
    """Get DB instance if available."""
    db = RicoDB()
    return db if db.available else None


def _memory() -> RicoMemoryStore:
    """Get memory store instance."""
    return RicoMemoryStore()


def _bundle_to_profile(bundle: dict[str, Any]) -> RicoProfile:
    """Convert a RicoDB.get_user_bundle() row into a RicoProfile with validation."""
    pdata: dict[str, Any] = bundle.get("profile") or {}
    sdata: dict[str, Any] = bundle.get("settings") or {}

    # Build settings with defaults for missing fields
    settings = RicoAgentSettings(
        autonomy_level=sdata.get("autonomy_level", "recommend_only"),
        communication_style=sdata.get("communication_style", "professional"),
        match_strictness=sdata.get("match_strictness", "balanced"),
        can_reject_unsuitable_jobs=sdata.get("can_reject_unsuitable_jobs", True),
        can_learn_from_actions=sdata.get("can_learn_from_actions", True),
        can_personalize_recommendations=sdata.get("can_personalize_recommendations", True),
        can_generate_cover_letters=sdata.get("can_generate_cover_letters", True),
        can_generate_recruiter_messages=sdata.get("can_generate_recruiter_messages", True),
        can_prepare_interview_notes=sdata.get("can_prepare_interview_notes", True),
        can_send_follow_up_reminders=sdata.get("can_send_follow_up_reminders", True),
        can_create_weekly_report=sdata.get("can_create_weekly_report", True),
    )

    # Build profile with proper type conversion
    return RicoProfile(
        user_id=bundle.get("external_user_id") or str(bundle.get("id", "")),
        name=bundle.get("name"),
        email=bundle.get("email"),
        phone=bundle.get("phone"),
        telegram_username=bundle.get("telegram_username"),
        target_roles=pdata.get("target_roles") or [],
        preferred_cities=pdata.get("preferred_cities") or [],
        salary_expectation_aed=pdata.get("salary_expectation_aed"),
        minimum_salary_aed=pdata.get("minimum_salary_aed"),
        skills=pdata.get("skills") or [],
        industries=pdata.get("industries") or [],
        visa_status=pdata.get("visa_status"),
        notice_period=pdata.get("notice_period"),
        years_experience=pdata.get("years_experience"),
        current_role=pdata.get("current_role"),
        current_company=pdata.get("current_company"),
        linkedin_url=pdata.get("linkedin_url"),
        portfolio_url=pdata.get("portfolio_url"),
        deal_breakers=pdata.get("deal_breakers") or [],
        green_flags=pdata.get("green_flags") or [],
        red_flags=pdata.get("red_flags") or [],
        cv_filename=pdata.get("cv_filename"),
        cv_status=pdata.get("cv_status"),
        profile_creation_mode=pdata.get("profile_creation_mode"),
        manual_profile_wizard_disabled=pdata.get("manual_profile_wizard_disabled", False),
        settings=settings,
    )


# ============================================================================
# Profile CRUD Operations
# ============================================================================

def get_profile(user_id: str) -> RicoProfile | None:
    """Load profile: DB first, JSON fallback."""
    db = _db()
    if db:
        try:
            bundle = db.get_user_bundle(user_id)
            if bundle:
                return _bundle_to_profile(bundle)
        except Exception as e:
            logger.exception("profile_repo: get_profile DB failed user_id=%s", user_id)

    return _memory().load_profile(user_id)


def upsert_profile(user_id: str, updates: dict[str, Any]) -> RicoProfile:
    """Write profile to DB (primary) and JSON (fallback mirror) with transaction safety."""
    # Filter updates to valid fields
    filtered_updates = {
        k: v for k, v in updates.items()
        if k in _PROFILE_FIELDS and v is not None
    }

    # ── JSON mirror (always) — keeps existing code working ────────────────────
    mem = _memory()
    profile = mem.upsert_profile_from_dict(user_id=user_id, updates=filtered_updates)

    # ── DB primary with transaction ───────────────────────────────────────────
    db = _db()
    if not db:
        return profile

    try:
        with _db_transaction() as conn:
            if not conn:
                return profile

            # 1. Upsert user record
            user_payload = {
                "external_user_id": user_id,
                "name": filtered_updates.get("name"),
                "email": filtered_updates.get("email"),
                "phone": filtered_updates.get("phone"),
                "telegram_username": filtered_updates.get("telegram_username"),
            }
            user_payload = {k: v for k, v in user_payload.items() if v is not None}
            user_row = db.upsert_user(user_payload, conn=conn)
            db_user_id = str(user_row["id"])

            # 2. Upsert profile JSONB
            profile_data = {
                k: v for k, v in filtered_updates.items()
                if k in _PROFILE_JSONB_FIELDS
            }
            if profile_data:
                db.upsert_profile(db_user_id, profile_data, conn=conn)

            # 3. Upsert settings
            settings_data = {}

            # Direct settings fields
            for k in _SETTINGS_FIELDS:
                if k in filtered_updates and filtered_updates[k] is not None:
                    settings_data[k] = filtered_updates[k]

            # Settings object (if passed as dict)
            if "settings" in filtered_updates and filtered_updates["settings"]:
                settings_obj = filtered_updates["settings"]
                if is_dataclass(settings_obj):
                    settings_obj = asdict(settings_obj)
                for k, v in settings_obj.items():
                    if k in _SETTINGS_FIELDS and v is not None:
                        settings_data[k] = v

            if settings_data:
                db.upsert_settings(db_user_id, settings_data, conn=conn)

        logger.debug("profile_repo: upsert_profile DB success user_id=%s", user_id)

    except Exception as e:
        logger.exception("profile_repo: upsert_profile DB failed user_id=%s", user_id)
        # Don't re-raise - we have JSON fallback

    return profile


def delete_profile(user_id: str) -> bool:
    """Delete a user profile and all associated data."""
    db = _db()
    if not db:
        # Delete from memory store only
        _memory().delete_profile(user_id)
        return True

    try:
        with _db_transaction() as conn:
            if not conn:
                return False

            bundle = db.get_user_bundle(user_id, conn=conn)
            if not bundle:
                return False

            db_user_id = str(bundle["id"])

            # Delete in correct order (child tables first)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rico_saved_searches WHERE user_id = %s", (db_user_id,))
                cur.execute("DELETE FROM rico_profiles WHERE user_id = %s", (db_user_id,))
                cur.execute("DELETE FROM rico_settings WHERE user_id = %s", (db_user_id,))
                cur.execute("DELETE FROM rico_users WHERE id = %s", (db_user_id,))

        # Also delete from memory store
        _memory().delete_profile(user_id)

        logger.info("profile_repo: deleted profile user_id=%s", user_id)
        return True

    except Exception as e:
        logger.exception("profile_repo: delete_profile failed user_id=%s", user_id)
        return False


# ============================================================================
# Preferences Operations
# ============================================================================

def get_preferences(user_id: str) -> dict[str, Any]:
    """Return agent/scoring/notification preferences from DB, or defaults."""
    db = _db()
    if db:
        try:
            bundle = db.get_user_bundle(user_id)
            if bundle and bundle.get("settings"):
                return dict(bundle["settings"])
        except Exception as e:
            logger.exception("profile_repo: get_preferences DB failed user_id=%s", user_id)

    profile = _memory().load_profile(user_id)
    if profile:
        return asdict(profile.settings)

    # Return defaults
    return asdict(RicoAgentSettings())


def save_preferences(user_id: str, prefs: dict[str, Any]) -> bool:
    """Persist preferences to DB with transaction safety."""
    # Validate preference keys
    valid_prefs = {k: v for k, v in prefs.items() if k in _SETTINGS_FIELDS}
    if not valid_prefs:
        return False

    db = _db()
    if not db:
        # Save to memory only
        profile = _memory().load_profile(user_id)
        if profile:
            for k, v in valid_prefs.items():
                if hasattr(profile.settings, k):
                    setattr(profile.settings, k, v)
            _memory().upsert_profile_from_dict(user_id, asdict(profile))
        return True

    try:
        with _db_transaction() as conn:
            if not conn:
                return False

            user_row = db.upsert_user({"external_user_id": user_id}, conn=conn)
            db_user_id = str(user_row["id"])
            db.upsert_settings(db_user_id, valid_prefs, conn=conn)

        logger.debug("profile_repo: saved preferences user_id=%s", user_id)
        return True

    except Exception as e:
        logger.exception("profile_repo: save_preferences DB failed user_id=%s", user_id)
        return False


# ============================================================================
# Saved Search Operations
# ============================================================================

def save_search(
    user_id: str,
    query: str,
    filters: dict[str, Any] | None = None,
    search_id: str | None = None,
) -> str | None:
    """Persist a saved search for a user with idempotent upsert."""
    db = _db()
    if not db:
        logger.debug("profile_repo: save_search skipped — DB unavailable user_id=%s", user_id)
        return None

    try:
        with _db_transaction() as conn:
            if not conn:
                return None

            user_row = db.upsert_user({"external_user_id": user_id}, conn=conn)
            db_user_id = str(user_row["id"])

            # Use upsert pattern with ON CONFLICT (if unique constraint exists)
            # Fallback to simple insert if constraint doesn't exist
            try:
                with conn.cursor() as cur:
                    if search_id:
                        # Update existing
                        cur.execute(
                            """
                            UPDATE rico_saved_searches
                            SET query = %s, filters = %s, updated_at = NOW()
                            WHERE id = %s AND user_id = %s
                            RETURNING id
                            """,
                            (query.strip(), Json(filters or {}), search_id, db_user_id)
                        )
                        result = cur.fetchone()
                        if result:
                            return str(result["id"])

                    # Try upsert by unique constraint (user_id, query)
                    cur.execute(
                        """
                        INSERT INTO rico_saved_searches (user_id, query, filters)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id, query)
                        DO UPDATE SET filters = EXCLUDED.filters, updated_at = NOW()
                        RETURNING id
                        """,
                        (db_user_id, query.strip(), Json(filters or {}))
                    )
                    row = cur.fetchone()
                    if row:
                        return str(row["id"])
            except Exception:
                # Fallback to simple insert if ON CONFLICT not supported
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO rico_saved_searches (user_id, query, filters) VALUES (%s, %s, %s) RETURNING id",
                        (db_user_id, query.strip(), Json(filters or {}))
                    )
                    row = cur.fetchone()
                    if row:
                        return str(row["id"])

        logger.info("profile_repo: saved_search persisted user_id=%s query=%r", user_id, query)
        return None

    except Exception as e:
        logger.exception("profile_repo: save_search DB failed user_id=%s", user_id)
        return None


def list_saved_searches(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return saved searches for a user, newest first."""
    db = _db()
    if not db:
        return []

    try:
        bundle = db.get_user_bundle(user_id)
        if not bundle:
            return []

        db_user_id = str(bundle["id"])

        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, query, filters, created_at, updated_at
                    FROM rico_saved_searches
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (db_user_id, limit),
                )
                rows = cur.fetchall()

        searches = []
        for row in rows:
            search = dict(row)
            # Convert Json type to dict if needed
            if 'filters' in search and hasattr(search['filters'], 'get'):
                search['filters'] = dict(search['filters'])
            searches.append(search)

        return searches

    except Exception as e:
        logger.exception("profile_repo: list_saved_searches DB failed user_id=%s", user_id)
        return []


def delete_search(user_id: str, search_id: str) -> bool:
    """Delete a saved search by ID."""
    db = _db()
    if not db:
        return False

    try:
        bundle = db.get_user_bundle(user_id)
        if not bundle:
            return False

        db_user_id = str(bundle["id"])

        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM rico_saved_searches WHERE id = %s AND user_id = %s",
                    (search_id, db_user_id)
                )
                deleted = cur.rowcount > 0
            conn.commit()

        if deleted:
            logger.info("profile_repo: deleted search user_id=%s search_id=%s", user_id, search_id)

        return deleted

    except Exception as e:
        logger.exception("profile_repo: delete_search DB failed user_id=%s", user_id)
        return False


def get_search_by_id(user_id: str, search_id: str) -> dict[str, Any] | None:
    """Get a single saved search by ID."""
    db = _db()
    if not db:
        return None

    try:
        bundle = db.get_user_bundle(user_id)
        if not bundle:
            return None

        db_user_id = str(bundle["id"])

        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, query, filters, created_at, updated_at
                    FROM rico_saved_searches
                    WHERE id = %s AND user_id = %s
                    """,
                    (search_id, db_user_id)
                )
                row = cur.fetchone()

        if row:
            search = dict(row)
            if 'filters' in search and hasattr(search['filters'], 'get'):
                search['filters'] = dict(search['filters'])
            return search

        return None

    except Exception as e:
        logger.exception("profile_repo: get_search_by_id failed user_id=%s", user_id)
        return None


# ============================================================================
# Batch Operations for Analytics
# ============================================================================

def get_profiles_by_role(target_role: str, limit: int = 100) -> list[RicoProfile]:
    """Get profiles that have a specific target role (for admin/analytics)."""
    db = _db()
    if not db:
        return []

    try:
        with db.connect() as conn:
            with conn.cursor() as cur:
                # Use JSONB array contains operator for proper array matching
                cur.execute(
                    """
                    SELECT u.*, p.data as profile_data, s.data as settings_data
                    FROM rico_users u
                    LEFT JOIN rico_profiles p ON p.user_id = u.id
                    LEFT JOIN rico_settings s ON s.user_id = u.id
                    WHERE p.data->'target_roles' ? %s
                    LIMIT %s
                    """,
                    (target_role, limit)
                )
                rows = cur.fetchall()

        profiles = []
        for row in rows:
            bundle = {
                "id": row["id"],
                "external_user_id": row["external_user_id"],
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "telegram_username": row["telegram_username"],
                "profile": row["profile_data"] or {},
                "settings": row["settings_data"] or {},
            }
            profiles.append(_bundle_to_profile(bundle))

        return profiles

    except Exception as e:
        logger.exception("profile_repo: get_profiles_by_role failed")
        return []


def export_profile_data(user_id: str) -> dict[str, Any] | None:
    """Export profile data for compliance/analytics (renamed from csv)."""
    profile = get_profile(user_id)
    if not profile:
        return None

    # Remove sensitive fields for export
    export_data = asdict(profile)
    sensitive_fields = {"phone", "email", "linkedin_url", "portfolio_url"}
    for field in sensitive_fields:
        export_data.pop(field, None)

    export_data["exported_at"] = str(datetime.now(_UTC))
    return export_data


# ============================================================================
# Identity Candidate Lookup (#97)
# ============================================================================

def _bundle_rows_to_profiles(rows: list[Any]) -> list[Any]:
    """Convert raw DB rows to ProfileContext via RicoProfile bundles."""
    profiles = []
    seen_ids = set()
    for row in rows:
        user_id = str(row.get("id", ""))
        if not user_id or user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        bundle = {
            "id": row["id"],
            "external_user_id": row["external_user_id"],
            "name": row["name"],
            "email": row["email"],
            "phone": row["phone"],
            "telegram_username": row["telegram_username"],
            "profile": row.get("profile_data") or {},
            "settings": row.get("settings_data") or {},
        }
        rico_profile = _bundle_to_profile(bundle)
        profiles.append(resolve_profile_context(user_id, rico_profile))
    return profiles


def find_profiles_by_email(email: str) -> list[Any]:
    """Find profiles by email (case-insensitive exact match)."""
    if not email:
        return []
    email_norm = email.strip().lower()
    candidates = []

    db = _db()
    if db:
        try:
            with db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT u.*, p.data as profile_data, s.data as settings_data
                        FROM rico_users u
                        LEFT JOIN rico_profiles p ON p.user_id = u.id
                        LEFT JOIN rico_settings s ON s.user_id = u.id
                        WHERE LOWER(u.email) = %s
                        LIMIT 10
                        """,
                        (email_norm,)
                    )
                    rows = cur.fetchall()
                    candidates.extend(_bundle_rows_to_profiles(rows))
        except Exception:
            logger.exception("profile_repo: find_profiles_by_email failed email=%s", email_norm)

    # Memory fallback — linear scan over JSON profiles
    if not candidates:
        for user_id in _memory().list_profiles():
            profile = _memory().load_profile(user_id)
            if profile and getattr(profile, "email", None):
                if str(profile.email).strip().lower() == email_norm:
                    candidates.append(resolve_profile_context(user_id, profile))

    return candidates


def find_profiles_by_phone(phone: str) -> list[Any]:
    """Find profiles by phone (digits-only match)."""
    if not phone:
        return []
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 7:
        return []
    candidates = []

    db = _db()
    if db:
        try:
            with db.connect() as conn:
                with conn.cursor() as cur:
                    # Remove non-digits from stored phone and compare last N digits
                    cur.execute(
                        """
                        SELECT u.*, p.data as profile_data, s.data as settings_data
                        FROM rico_users u
                        LEFT JOIN rico_profiles p ON p.user_id = u.id
                        LEFT JOIN rico_settings s ON s.user_id = u.id
                        WHERE REGEXP_REPLACE(u.phone, '[^0-9]', '', 'g') LIKE %s
                        LIMIT 10
                        """,
                        (f"%{digits}",)
                    )
                    rows = cur.fetchall()
                    candidates.extend(_bundle_rows_to_profiles(rows))
        except Exception:
            logger.exception("profile_repo: find_profiles_by_phone failed phone=%s", digits)

    # Memory fallback
    if not candidates:
        for user_id in _memory().list_profiles():
            profile = _memory().load_profile(user_id)
            if profile and getattr(profile, "phone", None):
                p_digits = "".join(ch for ch in str(profile.phone) if ch.isdigit())
                if digits in p_digits or p_digits in digits:
                    candidates.append(resolve_profile_context(user_id, profile))

    return candidates


def find_profiles_by_telegram_username(username: str) -> list[Any]:
    """Find profiles by telegram username (case-insensitive, @ stripped)."""
    if not username:
        return []
    username_norm = username.strip().lstrip("@").lower()
    if not username_norm:
        return []
    candidates = []

    db = _db()
    if db:
        try:
            with db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT u.*, p.data as profile_data, s.data as settings_data
                        FROM rico_users u
                        LEFT JOIN rico_profiles p ON p.user_id = u.id
                        LEFT JOIN rico_settings s ON s.user_id = u.id
                        WHERE LOWER(u.telegram_username) = %s
                        LIMIT 10
                        """,
                        (username_norm,)
                    )
                    rows = cur.fetchall()
                    candidates.extend(_bundle_rows_to_profiles(rows))
        except Exception:
            logger.exception(
                "profile_repo: find_profiles_by_telegram_username failed username=%s",
                username_norm,
            )

    # Memory fallback
    if not candidates:
        for user_id in _memory().list_profiles():
            profile = _memory().load_profile(user_id)
            if profile and getattr(profile, "telegram_username", None):
                if str(profile.telegram_username).strip().lstrip("@").lower() == username_norm:
                    candidates.append(resolve_profile_context(user_id, profile))

    return candidates


def find_identity_candidates(signal: IdentitySignal) -> list[Any]:
    """Collect all candidate profiles that might match an incoming identity signal.

    De-duplicates across email, phone, and telegram lookups.
    """
    candidates_by_id: dict[str, Any] = {}

    if signal.email:
        for p in find_profiles_by_email(signal.email):
            candidates_by_id[p.user_id] = p

    if signal.phone:
        for p in find_profiles_by_phone(signal.phone):
            candidates_by_id[p.user_id] = p

    if signal.telegram_username:
        for p in find_profiles_by_telegram_username(signal.telegram_username):
            candidates_by_id[p.user_id] = p

    return list(candidates_by_id.values())


# ============================================================================
# Health Check
# ============================================================================

def health_check() -> dict[str, Any]:
    """Check database connectivity and return status."""
    db = _db()
    if not db:
        return {"status": "degraded", "db_available": False, "fallback_active": True}

    try:
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "db_available": True, "fallback_active": False}
    except Exception as e:
        return {"status": "unhealthy", "db_available": False, "error": str(e), "fallback_active": True}
