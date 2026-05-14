"""
src/api/routers/jobs.py
Thin HTTP layer for job actions. All logic lives in src.services.jobs_service.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_current_user
from src.schemas.jobs import JobActionRequest, JobActionResponse, JobListResponse
from src.services.apply_service import apply_to_job
from src.services.jobs_service import (
    block_company,
    get_job,
    list_jobs,
    save_job,
    skip_job,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
def get_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    min_score: int = Query(0, ge=0, le=100),
    source: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    return list_jobs(page=page, limit=limit, min_score=min_score, source=source)


@router.get("/{job_id}")
def get_job_by_id(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job


@router.post("/{job_id}/apply", response_model=JobActionResponse)
def apply_job(
    job_id: str,
    req: Optional[JobActionRequest] = None,
    current_user: dict = Depends(get_current_user),
) -> JobActionResponse:
    user_id = str(current_user.get("id", ""))
    # Fetch job server-side to validate job_id
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    # If client provided job object, validate it matches server-side job_id
    if req and req.job:
        client_job_id = req.job.get("job_id") or req.job.get("id")
        if client_job_id and str(client_job_id) != job_id:
            raise HTTPException(status_code=422, detail="Job object in request body does not match job_id in URL")
    result = apply_to_job(job)
    return JobActionResponse(
        status=result.get("status", "unknown"),
        message=result.get("message", ""),
        job_id=result.get("job_id"),
    )


@router.post("/{job_id}/skip", response_model=JobActionResponse)
def skip_job_route(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> JobActionResponse:
    user_id = str(current_user.get("id", ""))
    # Fetch job server-side to validate job_id
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    skipped = skip_job(job, user_id=user_id)
    if skipped:
        return JobActionResponse(status="skipped", message="Job skipped and persisted")
    return JobActionResponse(status="already_tracked", message="Job was already tracked")


@router.post("/{job_id}/save", response_model=JobActionResponse)
def save_job_route(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> JobActionResponse:
    user_id = str(current_user.get("id", ""))
    # Fetch job server-side to validate job_id
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    saved = save_job(job, user_id=user_id)
    if saved:
        return JobActionResponse(status="saved", message="Job saved and persisted")
    return JobActionResponse(status="already_tracked", message="Job was already tracked")


@router.post("/{job_id}/block", response_model=JobActionResponse)
def block_job_route(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> JobActionResponse:
    user_id = str(current_user.get("id", ""))
    # Fetch job server-side to validate job_id
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    try:
        company = block_company(job, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return JobActionResponse(
        status="blocked",
        message=f"Blocked: {company}. This block is scoped to your account.",
    )
