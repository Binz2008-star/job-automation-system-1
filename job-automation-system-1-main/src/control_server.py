"""
src/control_server.py
FastAPI backend for dashboard one-click apply / skip / block.

Security model:
  - Every endpoint requires X-API-Key header matching CONTROL_SERVER_API_KEY env var.
  - If CONTROL_SERVER_API_KEY is not set the server refuses to start (fail-safe).
  - All actions are persisted to DB/JSON and logged for audit.
  - Learning repository updated with user feedback signals.

Endpoints:
  POST /apply-one      - Apply to a single job via NaukriGulf
  POST /skip-job       - Mark job as skipped (won't appear again)
  POST /block-similar  - Block company + similar titles
  POST /feedback       - Record user feedback (thumbs up/down)
  GET  /health         - Health check
  GET  /stats          - Dashboard statistics
"""

import json
import logging
import os
import secrets
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

from fastapi import Depends, FastAPI, HTTPException, Security, BackgroundTasks
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, validator

# Import pipeline components
from src.naukrigulf_apply import run_naukrigulf_apply, NGApplyStatus
from src.applications import mark_applied, is_applied, get_applied_jobs
from src.filter import save_seen_jobs
from src.profile import get_candidate_profile, get_target_roles
from src.repositories.learning_repo import get_learning_repository
from src.decision_engine import JobDecisionEngine

# Configure logging externally (not basicConfig in library context)
logger = logging.getLogger(__name__)

_UTC = timezone.utc

# ─── API-key authentication ────────────────────────────────────────────────────

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)
_API_KEY: str = os.getenv("CONTROL_SERVER_API_KEY", "")

# Path for persistent block list
BLOCKED_COMPANIES_FILE = Path(os.getenv("BLOCKED_COMPANIES_FILE", "data/blocked_companies.json"))
BLOCKED_KEYWORDS_FILE = Path(os.getenv("BLOCKED_KEYWORDS_FILE", "data/blocked_keywords.json"))


def _ensure_block_files() -> None:
    """Ensure block list files exist."""
    BLOCKED_COMPANIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not BLOCKED_COMPANIES_FILE.exists():
        _atomic_write_json(BLOCKED_COMPANIES_FILE, {"companies": [], "keywords": []})


def _atomic_write_json(file_path: Path, data: Any) -> None:
    """Write JSON file atomically to prevent partial writes."""
    tmp_path = file_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.replace(file_path)
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise e


def _require_api_key(key: str = Security(_API_KEY_HEADER)) -> None:
    """Dependency: reject every request that lacks a valid API key."""
    if not _API_KEY:
        raise HTTPException(
            status_code=503,
            detail="CONTROL_SERVER_API_KEY is not configured. Set it in .env before starting the server.",
        )
    if not secrets.compare_digest(key, _API_KEY):
        raise HTTPException(status_code=403, detail="Invalid API key")


def _load_blocked_companies() -> Dict[str, Any]:
    """Load persistent blocked companies list."""
    try:
        if BLOCKED_COMPANIES_FILE.exists():
            return json.loads(BLOCKED_COMPANIES_FILE.read_text())
    except Exception as e:
        logger.error(f"Failed to load blocked companies: {e}")
    return {"companies": [], "keywords": []}


def _save_blocked_companies(data: Dict[str, Any]) -> None:
    """Save blocked companies to persistent storage using atomic writes."""
    _atomic_write_json(BLOCKED_COMPANIES_FILE, data)


def _add_blocked_company(company: str) -> None:
    """Add company to persistent block list."""
    data = _load_blocked_companies()
    company_lower = company.strip().lower()
    if company_lower not in [c.lower() for c in data["companies"]]:
        data["companies"].append(company)
        _save_blocked_companies(data)
        logger.info(f"blocked_company_added company={company}")


def _add_blocked_keyword(keyword: str) -> None:
    """Add title keyword to persistent block list."""
    data = _load_blocked_companies()
    keyword_lower = keyword.strip().lower()
    if keyword_lower not in [k.lower() for k in data["keywords"]]:
        data["keywords"].append(keyword)
        _save_blocked_companies(data)
        logger.info(f"blocked_keyword_added keyword={keyword}")


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ApplyRequest(BaseModel):
    job: Dict[str, Any]
    user_id: Optional[str] = None


class ApplyResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    timestamp: Optional[str] = None


class SkipRequest(BaseModel):
    job: Dict[str, Any]
    reason: Optional[str] = Field(None, max_length=200)
    user_id: Optional[str] = None


class BlockRequest(BaseModel):
    job: Dict[str, Any]
    block_type: Literal["company", "keyword", "both"]
    user_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    job: Dict[str, Any]
    feedback_type: Literal["positive", "negative", "neutral"]
    rating: int = Field(1, ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=500)
    user_id: Optional[str] = None

    @validator("rating")
    def validate_rating(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("Rating must be between 1 and 5")
        return v


class FeedbackResponse(BaseModel):
    status: str
    message: str
    signal_recorded: bool
    learning_weight: float


class StatsResponse(BaseModel):
    total_applications: int
    pending_responses: int
    interview_rate: float
    blocked_companies: int
    saved_learning_signals: int
    last_24h_applications: int
    top_preferences: Dict[str, List[str]]


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Job Automation Control Server",
    version="2.0.0",
    description="Human-supervised autonomous recruitment with persistent learning. All endpoints require X-API-Key.",
)


@app.on_event("startup")
async def startup_event():
    """Initialize on server startup."""
    _ensure_block_files()
    logger.info("control_server_started api_key_configured={}".format(bool(_API_KEY)))


@app.get("/")
def read_root() -> Dict[str, str]:
    return {"status": "ready", "service": "Job Automation Control Server", "version": "2.0.0"}


@app.post("/apply-one", response_model=ApplyResponse, dependencies=[Depends(_require_api_key)])
async def apply_one(req: ApplyRequest, background_tasks: BackgroundTasks) -> ApplyResponse:
    """Apply to a single NaukriGulf job via browser automation."""
    try:
        job_title = req.job.get("title", "Unknown")
        company = req.job.get("company", "Unknown")
        logger.info("apply_request title=%r company=%r user=%s", job_title, company, req.user_id or "anonymous")

        # Validate job has required fields
        if not req.job.get("link"):
            return ApplyResponse(
                status="error",
                message="Job missing required link field",
                job_title=job_title,
                company=company
            )

        # Only NaukriGulf supported for now
        if "naukrigulf.com" not in req.job.get("link", "").lower():
            return ApplyResponse(
                status="error",
                message="Only NaukriGulf jobs are currently supported",
                job_title=job_title,
                company=company
            )

        # Run application
        results = run_naukrigulf_apply(jobs=[req.job], max_applies=1)

        if not results:
            return ApplyResponse(
                status="no_result",
                message="No application result returned",
                job_title=job_title,
                company=company
            )

        result = results[0]

        # Record in learning repository if successful
        if result.status == NGApplyStatus.SUCCESS and req.user_id:
            background_tasks.add_task(
                _record_learning_signal,
                req.user_id,
                "applied",
                job_title,
                company,
                0.8
            )

        return ApplyResponse(
            status=result.status.value,
            message=result.message or f"Applied to {job_title}",
            job_id=result.job_id,
            job_title=job_title,
            company=company,
            timestamp=result.timestamp.isoformat() if result.timestamp else None,
        )

    except Exception as e:
        logger.error("apply_request_failed error=%s", e, exc_info=True)
        return ApplyResponse(
            status="error",
            message=f"Application failed: {str(e)[:200]}",
            job_title=req.job.get("title", "Unknown"),
            company=req.job.get("company", "Unknown")
        )


@app.post("/skip-job", response_model=ApplyResponse, dependencies=[Depends(_require_api_key)])
def skip_job(req: SkipRequest, background_tasks: BackgroundTasks) -> ApplyResponse:
    """
    Skip a job: marks it as applied with status 'skipped' so it won't surface again.
    Also persists to seen jobs to prevent re-fetching.
    """
    try:
        job = req.job
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        logger.info("skip_job title=%r company=%r reason=%s user=%s", title, company, req.reason, req.user_id or "anonymous")

        # Mark as applied with skipped status
        if not is_applied(job):
            mark_applied(
                job,
                status="skipped",
                notes=f"Skipped by user via dashboard. Reason: {req.reason or 'Not specified'}"
            )

            # Also add to seen jobs to prevent re-fetching
            try:
                save_seen_jobs([job])
            except Exception as e:
                logger.warning(f"Failed to save to seen_jobs: {e}")

        # Record negative learning signal
        if req.user_id:
            background_tasks.add_task(
                _record_learning_signal,
                req.user_id,
                "skipped",
                title,
                company,
                -0.3
            )

        return ApplyResponse(
            status="skipped",
            message=f"Skipped and persisted: {title}",
            job_title=title,
            company=company,
            timestamp=datetime.now(_UTC).isoformat()
        )

    except Exception as e:
        logger.error("skip_job_failed error=%s", e, exc_info=True)
        return ApplyResponse(
            status="error",
            message=f"Skip failed: {str(e)[:200]}",
            job_title=req.job.get("title", "Unknown"),
            company=req.job.get("company", "Unknown")
        )


@app.post("/block-similar", response_model=ApplyResponse, dependencies=[Depends(_require_api_key)])
def block_similar(req: BlockRequest, background_tasks: BackgroundTasks) -> ApplyResponse:
    """
    Block future jobs from the same company or with similar titles.
    Persists to JSON files for long-term memory.
    """
    try:
        job_title = req.job.get("title", "")
        job_company = req.job.get("company", "")
        logger.info("block_similar title=%r company=%r type=%s user=%s", job_title, job_company, req.block_type, req.user_id or "anonymous")

        if not job_company and req.block_type in ("company", "both"):
            return ApplyResponse(
                status="error",
                message="Job missing company field for company blocking",
                job_title=job_title,
                company=job_company
            )

        # Mark the job as skipped first
        if not is_applied(req.job):
            mark_applied(
                req.job,
                status="blocked",
                notes=f"Blocked by user via dashboard. Type: {req.block_type}"
            )

        # Add to persistent block lists (JSON files only, no os.environ mutation)
        if req.block_type in ("company", "both"):
            _add_blocked_company(job_company)

        if req.block_type in ("keyword", "both"):
            # Extract keywords from job title
            keywords = _extract_title_keywords(job_title)
            for keyword in keywords[:3]:  # Block top 3 keywords
                _add_blocked_keyword(keyword)

        # Record strong negative learning signal
        if req.user_id:
            background_tasks.add_task(
                _record_learning_signal,
                req.user_id,
                "blocked",
                job_title,
                job_company,
                -0.9
            )

        message_parts = []
        if req.block_type in ("company", "both"):
            message_parts.append(f"blocked company: {job_company}")
        if req.block_type in ("keyword", "both"):
            message_parts.append("blocked similar titles")

        return ApplyResponse(
            status="blocked",
            message=f"Persistently {' and '.join(message_parts)}",
            job_title=job_title,
            company=job_company,
            timestamp=datetime.now(_UTC).isoformat()
        )

    except Exception as e:
        logger.error("block_similar_failed error=%s", e, exc_info=True)
        return ApplyResponse(
            status="error",
            message=f"Block failed: {str(e)[:200]}",
            job_title=req.job.get("title", "Unknown"),
            company=req.job.get("company", "Unknown")
        )


@app.post("/feedback", response_model=FeedbackResponse, dependencies=[Depends(_require_api_key)])
def submit_feedback(req: FeedbackRequest, background_tasks: BackgroundTasks) -> FeedbackResponse:
    """
    Submit explicit feedback on a job match for learning.
    Records signal in learning repository with weight based on rating.
    """
    try:
        job_title = req.job.get("title", "Unknown")
        company = req.job.get("company", "Unknown")
        logger.info("feedback title=%r company=%r type=%s rating=%d user=%s",
                   job_title, company, req.feedback_type, req.rating, req.user_id or "anonymous")

        # Map rating to learning weight
        weight_map = {
            1: -0.6,   # Strong negative
            2: -0.3,   # Mild negative
            3: 0.0,    # Neutral
            4: 0.4,    # Mild positive
            5: 0.8,    # Strong positive
        }
        weight = weight_map.get(req.rating, 0.0)

        # Adjust for feedback type
        if req.feedback_type == "negative":
            weight = min(weight, -0.2)
        elif req.feedback_type == "positive":
            weight = max(weight, 0.3)

        signal_recorded = False

        if req.user_id:
            # Record in learning repository
            repo = get_learning_repository()
            signal_recorded = repo.record_signal(
                canonical_user_id=req.user_id,
                signal_type="feedback",
                signal_value=req.feedback_type,
                signal_weight=weight,
                source="dashboard_feedback",
                metadata={
                    "job_title": job_title,
                    "company": company,
                    "rating": req.rating,
                    "comment": req.comment,
                    "job_link": req.job.get("link"),
                }
            )

            # Also record skill/role signals for positive feedback
            if req.feedback_type == "positive" and req.rating >= 4:
                background_tasks.add_task(
                    _record_positive_feedback_signals,
                    req.user_id,
                    req.job
                )

        return FeedbackResponse(
            status="recorded",
            message=f"Feedback recorded for {job_title}",
            signal_recorded=signal_recorded,
            learning_weight=weight
        )

    except Exception as e:
        logger.error("feedback_failed error=%s", e, exc_info=True)
        return FeedbackResponse(
            status="error",
            message=f"Failed to record feedback: {str(e)[:200]}",
            signal_recorded=False,
            learning_weight=0.0
        )


@app.get("/stats", response_model=StatsResponse, dependencies=[Depends(_require_api_key)])
def get_stats() -> StatsResponse:
    """Get dashboard statistics including learning repository insights."""
    try:
        applications = get_applied_jobs()
        total_apps = len(applications)

        # Calculate response rates
        responded = [a for a in applications if a.get("status") in ("interview", "replied", "viewed")]
        pending = [a for a in applications if a.get("status") in ("applied", "decision_made")]
        interview_rate = (len([a for a in applications if a.get("status") == "interview"]) / total_apps * 100) if total_apps > 0 else 0

        # Get learning repository stats
        repo = get_learning_repository()
        profile = get_candidate_profile()
        user_id = profile.get("email", "unknown") if profile else "unknown"

        learning_profile = repo.get_learning_profile(user_id, apply_decay=True)

        # Get top preferences
        top_preferences = {
            "roles": [role for role, _ in repo.get_top_preferences(user_id, "role", limit=5)],
            "locations": [loc for loc, _ in repo.get_top_preferences(user_id, "location", limit=5)],
            "skills": [skill for skill, _ in repo.get_top_preferences(user_id, "skill", limit=10)],
        }

        # Count applications in last 24 hours
        day_ago = datetime.now(_UTC) - timedelta(days=1)
        recent_apps = len([a for a in applications if a.get("timestamp") and a["timestamp"] > day_ago])

        blocked_data = _load_blocked_companies()

        return StatsResponse(
            total_applications=total_apps,
            pending_responses=len(pending),
            interview_rate=round(interview_rate, 1),
            blocked_companies=len(blocked_data.get("companies", [])),
            saved_learning_signals=len(learning_profile.signal_history) if learning_profile else 0,
            last_24h_applications=recent_apps,
            top_preferences=top_preferences
        )

    except Exception as e:
        logger.error("stats_failed error=%s", e, exc_info=True)
        return StatsResponse(
            total_applications=0,
            pending_responses=0,
            interview_rate=0.0,
            blocked_companies=0,
            saved_learning_signals=0,
            last_24h_applications=0,
            top_preferences={"roles": [], "locations": [], "skills": []}
        )


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint - simplified for security."""
    return {"status": "healthy"}


# ─── Background task helpers ──────────────────────────────────────────────────

def _record_learning_signal(user_id: str, action: str, title: str, company: str, weight: float) -> None:
    """Record learning signal in background."""
    try:
        repo = get_learning_repository()

        # Record role preference
        if title:
            repo.record_signal(
                user_id,
                "role_preference",
                title,
                signal_weight=weight,
                source="control_server",
                metadata={"action": action, "company": company}
            )

        # Record company sentiment
        if company:
            repo.record_signal(
                user_id,
                "company_sentiment",
                company,
                signal_weight=weight * 0.7,
                source="control_server",
                metadata={"action": action}
            )

        logger.debug(f"learning_signal_recorded user={user_id} action={action} weight={weight}")
    except Exception as e:
        logger.warning(f"Failed to record learning signal: {e}")


def _record_positive_feedback_signals(user_id: str, job: Dict[str, Any]) -> None:
    """Record additional signals for positive feedback."""
    try:
        repo = get_learning_repository()

        # Extract skills from job description if available
        description = job.get("description", "")
        if description:
            # Simple skill extraction (could be enhanced with NLP)
            common_skills = ["python", "sql", "excel", "project management", "communication"]
            for skill in common_skills:
                if skill.lower() in description.lower():
                    repo.record_signal(
                        user_id,
                        "skill_relevance",
                        skill,
                        signal_weight=0.5,
                        source="positive_feedback",
                        metadata={"job_title": job.get("title")}
                    )

        # Boost location preference
        location = job.get("location", "")
        if location:
            repo.record_signal(
                user_id,
                "location_preference",
                location,
                signal_weight=0.6,
                source="positive_feedback"
            )

    except Exception as e:
        logger.warning(f"Failed to record positive feedback signals: {e}")


def _extract_title_keywords(title: str) -> List[str]:
    """Extract significant keywords from job title."""
    stopwords = {"a", "an", "and", "of", "the", "to", "for", "in", "on", "at"}
    words = re.findall(r'\b[a-z]{3,}\b', title.lower())
    keywords = [w for w in words if w not in stopwords]
    return list(set(keywords))  # Deduplicate


if __name__ == "__main__":
    import uvicorn

    if not _API_KEY:
        print("❌ CONTROL_SERVER_API_KEY is not set — refusing to start.")
        print("   Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'")
        print("   Then add to .env: CONTROL_SERVER_API_KEY=<your-secret>")
        raise SystemExit(1)

    print("🚀 Starting Job Automation Control Server v2.0.0 on http://127.0.0.1:8000")
    print("🔐 API key authentication enabled (X-API-Key header required)")
    print(f"📁 Blocked companies file: {BLOCKED_COMPANIES_FILE}")
    print("📊 Endpoints:")
    print("   POST /apply-one     - Apply to job")
    print("   POST /skip-job      - Skip job")
    print("   POST /block-similar - Block company/title")
    print("   POST /feedback      - Submit feedback for learning")
    print("   GET  /stats         - Dashboard statistics")
    print("   GET  /health        - Health check")

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
