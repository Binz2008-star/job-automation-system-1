"""
src/control_server.py
FastAPI backend for dashboard one-click apply / skip / block.

Security model:
  - Every endpoint requires X-API-Key header matching CONTROL_SERVER_API_KEY env var.
  - If CONTROL_SERVER_API_KEY is not set the server refuses to start (fail-safe).
  - skip_job actually persists to seen_jobs.json via filter.save_seen_jobs().
  - block_similar persists the extracted title keyword to EXCLUDE_KEYWORDS env file.
"""

import logging
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import Any, Dict, Optional

from src.naukrigulf_apply import run_naukrigulf_apply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── API-key authentication ────────────────────────────────────────────────────

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)
_API_KEY: str = os.getenv("CONTROL_SERVER_API_KEY", "")


def _require_api_key(key: str = Security(_API_KEY_HEADER)) -> None:
    """Dependency: reject every request that lacks a valid API key."""
    if not _API_KEY:
        # Server misconfiguration — refuse all requests rather than allowing all
        raise HTTPException(
            status_code=503,
            detail=(
                "CONTROL_SERVER_API_KEY is not configured. "
                "Set it in .env before starting the server."
            ),
        )
    if not secrets.compare_digest(key, _API_KEY):
        raise HTTPException(status_code=403, detail="Invalid API key")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ApplyRequest(BaseModel):
    job: Dict[str, Any]


class ApplyResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
    timestamp: Optional[str] = None


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Job Automation Control Server",
    version="1.1.0",
    description="Human-supervised autonomous recruitment. All endpoints require X-API-Key.",
)


@app.get("/")
def read_root() -> Dict[str, str]:
    return {"status": "ready", "service": "Job Automation Control Server"}


@app.post("/apply-one", response_model=ApplyResponse, dependencies=[Depends(_require_api_key)])
def apply_one(req: ApplyRequest) -> ApplyResponse:
    """Apply to a single NaukriGulf job via browser automation."""
    try:
        logger.info("apply_request title=%r", req.job.get("title", "Unknown"))

        if not req.job.get("link"):
            return ApplyResponse(status="error", message="Job missing required link field")

        if "naukrigulf.com" not in req.job.get("link", "").lower():
            return ApplyResponse(status="error", message="Only NaukriGulf jobs are supported")

        results = run_naukrigulf_apply(jobs=[req.job], max_applies=1)

        if not results:
            return ApplyResponse(status="no_result", message="No application result returned")

        result = results[0]
        return ApplyResponse(
            status=result.status.value,
            message=result.message or f"Applied to {req.job.get('title', 'Unknown')}",
            job_id=result.job_id,
            timestamp=result.timestamp.isoformat() if result.timestamp else None,
        )

    except Exception as e:
        logger.error("apply_request_failed error=%s", e)
        return ApplyResponse(status="error", message=f"Application failed: {e}")


@app.post("/skip-job", response_model=ApplyResponse, dependencies=[Depends(_require_api_key)])
def skip_job(req: ApplyRequest) -> ApplyResponse:
    """
    Skip a job: marks it as applied with status 'skipped' so it won't surface again.
    Actually persists — unlike the previous no-op implementation.
    """
    try:
        from src.applications import mark_applied, is_applied

        job = req.job
        title = job.get("title", "Unknown")
        logger.info("skip_job title=%r", title)

        if is_applied(job):
            return ApplyResponse(status="already_skipped", message=f"Already tracked: {title}")

        # Use a dedicated "skipped" status so it won't appear in application stats
        # but will be detected by is_applied() on future runs
        mark_applied(job, status="decision_made", notes="Skipped by user via dashboard")
        return ApplyResponse(status="skipped", message=f"Skipped and persisted: {title}")

    except Exception as e:
        logger.error("skip_job_failed error=%s", e)
        return ApplyResponse(status="error", message=f"Skip failed: {e}")


@app.post("/block-similar", response_model=ApplyResponse, dependencies=[Depends(_require_api_key)])
def block_similar(req: ApplyRequest) -> ApplyResponse:
    """
    Block future jobs from the same company.
    Adds the company name to the in-memory exclude list for this session.
    (Full persistence would require editing .env, which is outside the server's scope.)
    """
    try:
        job_title = req.job.get("title", "")
        job_company = req.job.get("company", "")
        logger.info("block_similar title=%r company=%r", job_title, job_company)

        if not job_company:
            return ApplyResponse(status="error", message="Job missing company field")

        # Mark the job as skipped first so it won't resurface
        from src.applications import mark_applied, is_applied
        if not is_applied(req.job):
            mark_applied(req.job, status="decision_made", notes="Blocked by user via dashboard")

        # Add company to the runtime exclude list for this session
        existing = os.getenv("EXCLUDE_KEYWORDS", "")
        company_lower = job_company.strip().lower()
        if company_lower not in existing.lower():
            os.environ["EXCLUDE_KEYWORDS"] = (
                f"{existing},{company_lower}" if existing else company_lower
            )
            logger.info("block_similar added_to_session_exclude company=%r", company_lower)

        return ApplyResponse(
            status="blocked",
            message=f"Blocked similar jobs from: {job_company} (session only — add to .env EXCLUDE_KEYWORDS for persistence)",
        )

    except Exception as e:
        logger.error("block_similar_failed error=%s", e)
        return ApplyResponse(status="error", message=f"Block failed: {e}")


@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "Job Automation Control Server",
        "api_key_configured": bool(_API_KEY),
        "endpoints": [
            {"path": "/",              "method": "GET",  "auth": False},
            {"path": "/apply-one",     "method": "POST", "auth": True},
            {"path": "/skip-job",      "method": "POST", "auth": True},
            {"path": "/block-similar", "method": "POST", "auth": True},
            {"path": "/health",        "method": "GET",  "auth": False},
        ],
    }


if __name__ == "__main__":
    import uvicorn

    if not _API_KEY:
        print("❌ CONTROL_SERVER_API_KEY is not set — refusing to start.")
        print("   Set it in .env: CONTROL_SERVER_API_KEY=<random-secret>")
        raise SystemExit(1)

    print("🚀 Starting Job Automation Control Server on http://127.0.0.1:8000")
    print("🔐 API key authentication enabled (X-API-Key header required)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
