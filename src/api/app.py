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

from src.api.auth import decode_access_token, router as auth_router
from src.api.rate_limit import limiter, rate_limit_exceeded_handler
from src.api.routers.actions import router as actions_router
from src.api.routers.agent import router as agent_router
from src.api.routers.applications import router as applications_router
from src.api.routers.rico_chat import router as rico_chat_router
from src.api.routers.jobs import router as jobs_router
from src.api.routers.onboarding import router as onboarding_router
from src.api.routers.pipeline import router as pipeline_router
from src.api.routers.settings import router as settings_router
from src.api.routers.stats import router as stats_router
from src.api.routers.subscription import router as subscription_router
from src.api.routers.user import router as user_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", os.getenv("RICO_ENV", "production")),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            integrations=[FastApiIntegration()],
        )
        logger.info("sentry_initialized environment=%s", os.getenv("SENTRY_ENVIRONMENT", os.getenv("RICO_ENV", "production")))
    except Exception:
        logger.exception("sentry_init_failed")


init_sentry()

_CRITICAL_TABLES = frozenset({"users", "action_audit_log", "password_reset_tokens"})


def _check_critical_tables() -> None:
    from src.db import get_db_connection
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                """,
                (list(_CRITICAL_TABLES),),
            )
            found = {row[0] for row in cur.fetchall()}
        missing = _CRITICAL_TABLES - found
        if missing:
            logger.error(
                "startup_check: missing tables %s — run pending migrations before serving traffic",
                sorted(missing),
            )
        else:
            logger.info("startup_check: critical tables present")
    except Exception as exc:
        logger.warning("startup_check: could not verify tables: %s", exc)
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from src.rico_db import RicoDB
        RicoDB().init()
        logger.info("rico_db_init OK")
    except Exception:
        logger.warning("rico_db_init skipped (DB unavailable or tables already exist)")

    try:
        from src.db import init_db
        init_db()
        logger.info("settings_migration OK")
    except Exception as exc:
        logger.warning("settings_migration failed: %s", exc)

    _check_critical_tables()
    yield


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

_DEFAULT_CORS_ORIGINS = ",".join(
    [
        "http://localhost:3000",
        "https://ricohunt.com",
        "https://www.ricohunt.com",
    ]
)
_origins_raw = os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
_origins_list = [o.strip() for o in _origins_raw.split(",") if o.strip()]
_wildcard = _origins_list == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _wildcard else _origins_list,
    allow_credentials=False if _wildcard else True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)


@app.middleware("http")
async def hydrate_request_auth_context(request: Request, call_next):
    request.state.current_user = None
    request.state.user_id = None
    request.state.access_token_present = False
    request.state.auth_cookie_invalid = False

    token = request.cookies.get("access_token")
    if token:
        request.state.access_token_present = True
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            user = {
                "email": payload["sub"],
                "role": payload.get("role", "user"),
            }
            request.state.current_user = user
            request.state.user_id = user["email"]
        else:
            request.state.auth_cookie_invalid = True

    return await call_next(request)


app.include_router(auth_router)
app.include_router(user_router)
app.include_router(actions_router)
app.include_router(agent_router)
app.include_router(rico_chat_router)
app.include_router(jobs_router)
app.include_router(applications_router)
app.include_router(stats_router)
app.include_router(settings_router)
app.include_router(onboarding_router)
app.include_router(pipeline_router)
app.include_router(subscription_router)
