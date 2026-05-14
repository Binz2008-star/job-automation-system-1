"""
src/repositories/applications_repo.py
User-scoped adapter over Rico DB (SaaS path).

SaaS-path contract:
  - Callers MUST supply user_id (derived from JWT via get_current_user_id dep).
  - DB unavailability raises HTTP 503.
  - User registered via /api/v1/auth/register is auto-provisioned in rico_users on
    first SaaS access (upsert with source='auth_register').
  - Transient DB errors propagate as 503, not 404.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

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
    """
    Map external user_id (email) to Rico DB internal UUID.

    Returns None only when the user genuinely has no rico_users row.
    Raises on DB/connection errors so callers can surface HTTP 503.
    """
    bundle = db.get_user_bundle(user_id)
    if bundle:
        return str(bundle["id"])
    return None


def _provision_db_user_id(db: Any, user_id: str) -> str:
    """
    Return the Rico DB UUID for ``user_id``, auto-provisioning a rico_users row
    if one does not yet exist (e.g. user registered via /api/v1/auth/register but
    has never gone through the Jotform onboarding webhook).

    Raises HTTPException 503 on any DB error so the caller surfaces a service
    failure rather than a misleading 404.
    """
    try:
        db_user_id = _resolve_db_user_id(db, user_id)
        if db_user_id:
            return db_user_id
        logger.info(
            "applications_repo: no rico_users row for user_id=%s — provisioning", user_id
        )
        row = db.upsert_user(
            {"external_user_id": user_id, "email": user_id, "source": "auth_register"}
        )
        return str(row["id"])
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "applications_repo: DB error resolving/provisioning user_id=%s", user_id
        )
        raise HTTPException(status_code=503, detail="Database error resolving user")


def _warn_legacy_fallback(operation: str) -> None:
    logger.warning("LEGACY_FALLBACK_NO_USER_ID operation=%s", operation)


# ── Public API ───────────────────────────────────────────────────────────────


def get_all(user_id: str) -> List[Dict[str, Any]]:
    """Load tracked applications for a specific user. user_id is required for authenticated access."""
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable")

    db_user_id = _provision_db_user_id(db, user_id)
    return db.get_recommendations(db_user_id, limit=200)


def get_stats(user_id: str) -> Dict[str, Any]:
    """Aggregate statistics for a specific user. user_id is required for authenticated access."""
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable")

    db_user_id = _provision_db_user_id(db, user_id)
    return db.get_recommendation_stats(db_user_id)


def find_by_job_id(job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Find a single application record by job_id for a user. user_id is required for authenticated access."""
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable")

    db_user_id = _provision_db_user_id(db, user_id)
    apps = db.get_recommendations(db_user_id, limit=200)
    return next(
        (a for a in apps if isinstance(a, dict) and a.get("job_id") == job_id),
        None,
    )


def update_status(
    job: Dict[str, Any], status: str, user_id: str, notes: str = ""
) -> bool:
    """Update application status for a specific user. user_id is required for authenticated access."""
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable")

    db_user_id = _provision_db_user_id(db, user_id)
    job_key = job.get("job_id", "")
    return db.update_recommendation_status(db_user_id, job_key, status, notes)
