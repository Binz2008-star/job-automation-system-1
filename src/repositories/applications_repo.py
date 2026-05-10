"""
src/repositories/applications_repo.py
User-scoped adapter over Rico DB (primary) with fallback to global JSON store.
All SaaS-path callers must supply ``user_id`` so data is isolated per user.
Legacy pipeline callers omit ``user_id`` to keep the old single-user JSON path.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.applications import (
    get_applied_jobs as _get_applied,
    get_application_stats as _get_stats,
    update_application_status as _update_status,
)

logger = logging.getLogger(__name__)

# ── Rico DB helpers ────────────────────────────────────────────────────────────


def _db() -> Any:
    from src.rico_db import RicoDB

    db = RicoDB()
    return db if db.available else None


def _resolve_db_user_id(db: Any, user_id: str) -> Optional[str]:
    """Map external user_id (email) to Rico DB internal UUID."""
    try:
        bundle = db.get_user_bundle(user_id)
        if bundle:
            return str(bundle["id"])
    except Exception:
        logger.exception("applications_repo: failed to resolve user_id=%s", user_id)
    return None


# ── Public API ───────────────────────────────────────────────────────────────


def get_all(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load tracked applications.  When ``user_id`` is given, Rico DB is used."""
    if not user_id:
        logger.warning("LEGACY_FALLBACK_NO_USER_ID: get_all")
        return _get_applied()

    db = _db()
    if not db:
        logger.warning("LEGACY_FALLBACK_DB_UNAVAILABLE: get_all user_id=%s", user_id)
        return _get_applied()

    db_user_id = _resolve_db_user_id(db, user_id)
    if not db_user_id:
        logger.warning("LEGACY_FALLBACK_USER_NOT_FOUND: get_all user_id=%s", user_id)
        return _get_applied()

    try:
        return db.get_recommendations(db_user_id, limit=200)
    except Exception:
        logger.exception("LEGACY_FALLBACK_DB_ERROR: get_all user_id=%s", user_id)
        return _get_applied()


def get_stats(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate statistics.  When ``user_id`` is given, Rico DB is used."""
    if not user_id:
        logger.warning("LEGACY_FALLBACK_NO_USER_ID: get_stats")
        return _get_stats()

    db = _db()
    if not db:
        logger.warning("LEGACY_FALLBACK_DB_UNAVAILABLE: get_stats user_id=%s", user_id)
        return _get_stats()

    db_user_id = _resolve_db_user_id(db, user_id)
    if not db_user_id:
        logger.warning("LEGACY_FALLBACK_USER_NOT_FOUND: get_stats user_id=%s", user_id)
        return _get_stats()

    try:
        return db.get_recommendation_stats(db_user_id)
    except Exception:
        logger.exception("LEGACY_FALLBACK_DB_ERROR: get_stats user_id=%s", user_id)
        return _get_stats()


def find_by_job_id(job_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find a single application record by its job_id hash."""
    if not user_id:
        logger.warning("LEGACY_FALLBACK_NO_USER_ID: find_by_job_id")
        return next(
            (a for a in _get_applied() if isinstance(a, dict) and a.get("job_id") == job_id),
            None,
        )

    db = _db()
    if not db:
        logger.warning("LEGACY_FALLBACK_DB_UNAVAILABLE: find_by_job_id user_id=%s", user_id)
        return next(
            (a for a in _get_applied() if isinstance(a, dict) and a.get("job_id") == job_id),
            None,
        )

    db_user_id = _resolve_db_user_id(db, user_id)
    if not db_user_id:
        logger.warning("LEGACY_FALLBACK_USER_NOT_FOUND: find_by_job_id user_id=%s", user_id)
        return next(
            (a for a in _get_applied() if isinstance(a, dict) and a.get("job_id") == job_id),
            None,
        )

    try:
        apps = db.get_recommendations(db_user_id, limit=200)
        return next(
            (a for a in apps if isinstance(a, dict) and a.get("job_id") == job_id),
            None,
        )
    except Exception:
        logger.exception("LEGACY_FALLBACK_DB_ERROR: find_by_job_id user_id=%s", user_id)
        return next(
            (a for a in _get_applied() if isinstance(a, dict) and a.get("job_id") == job_id),
            None,
        )


def update_status(
    job: Dict[str, Any], status: str, notes: str = "", user_id: Optional[str] = None
) -> bool:
    """Update application status.  When ``user_id`` is given, Rico DB is used."""
    if not user_id:
        logger.warning("LEGACY_FALLBACK_NO_USER_ID: update_status")
        return _update_status(job, status, notes)

    db = _db()
    if not db:
        logger.warning("LEGACY_FALLBACK_DB_UNAVAILABLE: update_status user_id=%s", user_id)
        return _update_status(job, status, notes)

    db_user_id = _resolve_db_user_id(db, user_id)
    if not db_user_id:
        logger.warning("LEGACY_FALLBACK_USER_NOT_FOUND: update_status user_id=%s", user_id)
        return _update_status(job, status, notes)

    try:
        job_key = job.get("job_id", "")
        return db.update_recommendation_status(db_user_id, job_key, status, notes)
    except Exception:
        logger.exception("LEGACY_FALLBACK_DB_ERROR: update_status user_id=%s", user_id)
        return _update_status(job, status, notes)
