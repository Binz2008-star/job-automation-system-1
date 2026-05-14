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
) -> Dict[str, Any]:
    """Paginated job list. DB preferred; applied_jobs.json fallback."""
    offset = (page - 1) * limit

    if is_db_available():
        result = jobs_repo.list_from_db(offset, limit, min_score, source)
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


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Single job by DB integer id or SHA-256 job_id hash."""
    if is_db_available() and job_id.isdigit():
        job = jobs_repo.get_by_db_id(int(job_id))
        if job:
            return job

    for job in get_applied_jobs():
        if not isinstance(job, dict):
            continue
        if get_job_id(job) == job_id or str(job.get("id", "")) == job_id:
            return job
    return None


def skip_job(job: Dict[str, Any]) -> bool:
    """Mark skipped. Returns True if newly persisted, False if already tracked."""
    if is_applied(job):
        return False
    return mark_applied(job, status="decision_made", notes="Skipped via API")


def save_job(job: Dict[str, Any]) -> bool:
    """Mark saved. Returns True if newly persisted, False if already tracked."""
    if is_applied(job):
        return False
    return mark_applied(job, status="saved", notes="Saved via API")


def block_company(job: Dict[str, Any]) -> str:
    """
    Block all future results from this company (session scope).
    Returns the blocked company name.
    Add to EXCLUDE_KEYWORDS in .env for cross-restart persistence.
    """
    company = (job.get("company") or "").strip()
    if not company:
        raise ValueError("Job missing company field")

    if not is_applied(job):
        mark_applied(job, status="decision_made", notes="Company blocked via API")

    existing = os.getenv("EXCLUDE_KEYWORDS", "")
    company_lower = company.lower()
    if company_lower not in existing.lower():
        os.environ["EXCLUDE_KEYWORDS"] = (
            f"{existing},{company_lower}" if existing else company_lower
        )
        logger.info("block_company added to session exclude company=%r", company_lower)

    return company
