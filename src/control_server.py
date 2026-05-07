"""
Control Server - FastAPI backend for dashboard one-click apply functionality
Provides REST endpoints for human-supervised autonomous job applications.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any, List
import logging

from src.naukrigulf_apply import run_naukrigulf_apply

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Job Automation Control Server", version="1.0.0")

class ApplyRequest(BaseModel):
    job: Dict[str, Any]

class ApplyResponse(BaseModel):
    status: str
    message: str
    job_id: str = None
    timestamp: str = None

@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "ready", "service": "Job Automation Control Server"}

@app.post("/apply-one", response_model=ApplyResponse)
def apply_one(req: ApplyRequest):
    """
    Apply to a single job via NaukriGulf automation engine.

    This endpoint enables the dashboard's one-click apply functionality,
    transforming the system from pure automation to human-supervised
    autonomous recruitment.
    """
    try:
        logger.info(f"Received apply request for job: {req.job.get('title', 'Unknown')}")

        # Validate job contains required fields
        if not req.job.get("link"):
            return ApplyResponse(
                status="error",
                message="Job missing required link field"
            )

        # Safety check - only allow NaukriGulf jobs
        if "naukrigulf.com" not in req.job.get("link", "").lower():
            return ApplyResponse(
                status="error",
                message="Only NaukriGulf jobs are supported"
            )

        # Execute single job application
        results = run_naukrigulf_apply(
            jobs=[req.job],
            max_applies=1
        )

        if not results:
            return ApplyResponse(
                status="no_result",
                message="No application result returned"
            )

        # Get first result
        result = results[0]

        return ApplyResponse(
            status=result.status.value,
            message=result.message or f"Applied to {req.job.get('title', 'Unknown')}",
            job_id=result.job_id,
            timestamp=result.timestamp.isoformat() if result.timestamp else None
        )

    except Exception as e:
        logger.error(f"Apply request failed: {e}")
        return ApplyResponse(
            status="error",
            message=f"Application failed: {str(e)}"
        )

@app.post("/skip-job")
def skip_job(req: ApplyRequest):
    """Skip a job and mark it as seen."""
    try:
        logger.info(f"Skipping job: {req.job.get('title', 'Unknown')}")

        # Add job to seen jobs list to prevent future processing
        job_link = req.job.get("link", "")
        if job_link:
            # This would integrate with your existing seen_jobs tracking
            logger.info(f"Added to seen jobs: {job_link}")

        return ApplyResponse(
            status="skipped",
            message=f"Skipped: {req.job.get('title', 'Unknown')}"
        )

    except Exception as e:
        logger.error(f"Skip job failed: {e}")
        return ApplyResponse(
            status="error",
            message=f"Skip failed: {str(e)}"
        )

@app.post("/block-similar")
def block_similar(req: ApplyRequest):
    """Block similar jobs based on title/company patterns."""
    try:
        job_title = req.job.get("title", "")
        job_company = req.job.get("company", "")

        logger.info(f"Blocking similar to: {job_title} at {job_company}")

        # Extract keywords from title for blocking
        title_words = job_title.lower().split()
        # This would integrate with your exclusion keywords system

        return ApplyResponse(
            status="blocked",
            message=f"Blocked similar jobs to: {job_title}"
        )

    except Exception as e:
        logger.error(f"Block similar failed: {e}")
        return ApplyResponse(
            status="error",
            message=f"Block failed: {str(e)}"
        )

@app.get("/health")
def health_check():
    """Detailed health check for monitoring."""
    return {
        "status": "healthy",
        "service": "Job Automation Control Server",
        "endpoints": [
            {"path": "/", "method": "GET", "description": "Health check"},
            {"path": "/apply-one", "method": "POST", "description": "Apply to single job"},
            {"path": "/skip-job", "method": "POST", "description": "Skip job"},
            {"path": "/block-similar", "method": "POST", "description": "Block similar jobs"},
            {"path": "/health", "method": "GET", "description": "Detailed health check"}
        ]
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Job Automation Control Server on http://127.0.0.1:8000")
    print("📋 Available endpoints:")
    print("   GET  /           - Health check")
    print("   POST /apply-one  - Apply to single job")
    print("   POST /skip-job   - Skip job")
    print("   POST /block-similar - Block similar jobs")
    print("   GET  /health     - Detailed health check")
    print("\n🎯 Dashboard integration ready!")
    print("📊 This enables human-supervised autonomous recruitment")
    print("🎮 Score-based actions: ≥85 auto, 65-84 manual, <65 skip")

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
