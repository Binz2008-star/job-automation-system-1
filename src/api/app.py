"""
src/api/app.py
Main FastAPI application for the Job Automation Platform API.

Startup:
    uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

All API endpoints live under /api/v1/.
The legacy control_server.py is preserved separately for backward compat.

Required env vars (see .env.example):
    ADMIN_EMAIL, ADMIN_PASSWORD or ADMIN_PASSWORD_HASH, JWT_SECRET (optional but recommended)
    DATABASE_URL (optional — JSON fallback active when absent)
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api.auth import router as auth_router
from src.api.rate_limit import limiter, rate_limit_exceeded_handler
from src.api.routers.actions import router as actions_router
from src.api.routers.agent import router as agent_router
from src.api.routers.applications import router as applications_router
from src.api.routers.rico_chat import router as rico_chat_router
from src.api.routers.jobs import router as jobs_router
from src.api.routers.pipeline import router as pipeline_router
from src.api.routers.settings import router as settings_router
from src.api.routers.stats import router as stats_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from src.rico_db import RicoDB
        RicoDB().init()
        logger.info("rico_db_init OK")
    except Exception:
        logger.warning("rico_db_init skipped (DB unavailable or tables already exist)")
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Job Automation Platform",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "REST API for the autonomous job search pipeline. "
        "All mutating endpoints require JWT authentication (httpOnly cookie)."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────

_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
_origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,   # required for httpOnly cookie auth
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(actions_router)
app.include_router(agent_router)
app.include_router(rico_chat_router)
app.include_router(jobs_router)
app.include_router(applications_router)
app.include_router(stats_router)
app.include_router(settings_router)
app.include_router(pipeline_router)

# ── Global error handler ─────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# ── Health + root ─────────────────────────────────────────────────────────────

@app.get("/")
def root() -> Dict[str, str]:
    return {
        "service": "Job Automation Platform",
        "status": "ready",
        "docs": "/api/docs",
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    from src.db import is_db_available
    from src.rico_env import get_rico_env_report
    rico = get_rico_env_report()
    return {
        "status": "healthy",
        "db": "connected" if is_db_available() else "json_fallback",
        "version": "1.0.0",
        "rico": {
            "ready_for_api":      rico.ready_for_api,
            "ready_for_db":       rico.ready_for_db,
            "ready_for_telegram": rico.ready_for_telegram,
            "ready_for_openai":   rico.ready_for_openai,
            "ready_for_jotform":  rico.ready_for_jotform,
        },
        "endpoints": {
            "auth":         "/api/v1/auth/login",
            "jobs":         "/api/v1/jobs",
            "applications": "/api/v1/applications",
            "stats":        "/api/v1/stats",
            "settings":     "/api/v1/settings",
            "pipeline":     "/api/v1/pipeline/status",
            "actions":      "/api/v1/actions/run",
            "rico_chat":    "/api/v1/rico/chat",
            "docs":         "/api/docs",
        },
    }


# ── Dev entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
