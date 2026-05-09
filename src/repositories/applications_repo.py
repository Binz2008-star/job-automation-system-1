"""
src/repositories/applications_repo.py
Thin adapter over src.applications for use by the service layer.
Keeps all file-locking / JSON-loading logic inside src.applications.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.applications import (
    get_applied_jobs as _get_applied,
    get_application_stats as _get_stats,
    update_application_status as _update_status,
)


def get_all() -> List[Dict[str, Any]]:
    """Load all tracked applications from the JSON store."""
    return _get_applied()


def get_stats() -> Dict[str, Any]:
    """Aggregate statistics for tracked applications."""
    return _get_stats()


def find_by_job_id(job_id: str) -> Optional[Dict[str, Any]]:
    """Find a single application record by its job_id hash."""
    return next(
        (a for a in _get_applied() if isinstance(a, dict) and a.get("job_id") == job_id),
        None,
    )


def update_status(job: Dict[str, Any], status: str, notes: str = "") -> bool:
    """Delegate status update to src.applications (which handles locking)."""
    return _update_status(job, status, notes)
