"""
src/services/jobs_service.py
Business logic for job listing and dashboard actions.
Calls repositories — never reaches into DB or files directly.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from src.applications import (
    get_applied_jobs,
    get_job_id,
    is_applied,
    mark_applied,
)
from src.db import is_db_available
from src.repositories import jobs_repo

logger = logging.getLogger(__name__)


def list_jobs(
    page: int = 1,
    limit: int = 20,
    min_score: int = 0,
    source: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Paginated job list. DB preferred; applied_jobs.json fallback."""
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    offset = (page - 1) * limit

    if is_db_available():
        result = jobs_repo.list_from_db(offset, limit, min_score, source, user_id=user_id)
        if result is not None:
            return result

    return _list_from_json(offset, limit, min_score)


def _list_from_json(offset: int, limit: int, min_score: int) -> Dict[str, Any]:
    from src.job_history import load_job_history
    all_jobs = load_job_history()
    filtered = [j for j in all_jobs if isinstance(j, dict) and j.get("score", 0) >= min_score]
    filtered.sort(key=lambda j: j.get("score", 0), reverse=True)
    total = len(filtered)
    page_jobs = filtered[offset : offset + limit]
    return {
        "jobs": page_jobs,
        "total": total,
        "page": offset // limit + 1,
        "limit": limit,
        "pages": max(1, -(-total // limit)),
    }


def get_job(job_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Single job by DB integer id or SHA-256 job_id hash."""
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    if is_db_available() and job_id.isdigit():
        job = jobs_repo.get_by_db_id(int(job_id), user_id=user_id)
        if job:
            return job

    for job in get_applied_jobs():
        if not isinstance(job, dict):
            continue
        if get_job_id(job) == job_id or str(job.get("id", "")) == job_id:
            return job
    return None


def skip_job(job: Dict[str, Any], user_id: Optional[str] = None) -> bool:
    """Mark skipped. Returns True if newly persisted, False if already tracked."""
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    if is_applied(job):
        return False
    return mark_applied(job, status="decision_made", notes="Skipped via API", user_id=user_id)


def save_job(job: Dict[str, Any], user_id: Optional[str] = None) -> bool:
    """Mark saved. Returns True if newly persisted, False if already tracked."""
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    if is_applied(job):
        return False
    return mark_applied(job, status="saved", notes="Saved via API", user_id=user_id)


def block_company(job: Dict[str, Any], user_id: Optional[str] = None) -> str:
    """
    Block company for this user only (user-scoped, not global).
    Returns the blocked company name.
    Does NOT modify EXCLUDE_KEYWORDS (which affects all users).
    """
    if not user_id:
        raise ValueError("user_id is required for authenticated access")

    company = (job.get("company") or "").strip()
    if not company:
        raise ValueError("Job missing company field")

    if not is_applied(job):
        mark_applied(job, status="decision_made", notes="Company blocked via API", user_id=user_id)

    # TODO: Store user-specific blocked companies in database table
    # For now, just mark the job as blocked for this user
    logger.info("block_company: user=%s blocked company=%r", user_id, company)

    return company
