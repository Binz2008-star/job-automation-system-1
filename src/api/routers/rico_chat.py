"""
src/api/routers/rico_chat.py
HTTP adapters that expose Rico AI flows through the layered API.
Rico internals are not modified — this is a pure routing shim.

Routes:
  POST /api/v1/rico/chat                        natural-language chat  (JWT required)
  GET  /api/v1/rico/profile                     user profile           (JWT required)
  GET  /api/v1/rico/settings/saved-searches     list saved searches    (JWT required)
  POST /api/v1/rico/settings/saved-searches     save a search          (JWT required)
  DELETE /api/v1/rico/settings/saved-searches/{id} delete saved search (JWT required)
  GET  /api/v1/rico/chat/history                conversation history   (JWT required)
  POST /api/v1/rico/feedback                    feedback on matches    (JWT required)
  GET  /api/v1/rico/openai-smoke                AI runtime probe       (JWT required)
  POST /api/v1/rico/upload-cv                   CV file upload + parsing
  GET  /api/v1/rico/metrics                     Prometheus metrics
  POST /api/v1/rico/webhooks/telegram           Telegram bot webhook (called by Telegram)
  POST /api/v1/rico/webhooks/jotform            Jotform onboarding webhook (called by Jotform)
  POST /api/v1/rico/webhooks/github             GitHub webhook (push, PR, issues, ping)
  POST /api/v1/rico/chat/public                 Public chat (no JWT, session-based, rate-limited)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from functools import wraps

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, validator

from src.api.deps import get_current_user, get_current_user_id
from src.api.rate_limit import LIMIT_CHAT, LIMIT_UPLOAD, LIMIT_WEBHOOK, limiter
from src.repositories.profile_repo import (
    get_profile,
    upsert_profile,
    list_saved_searches,
    save_search,
    delete_search,
)
from src.repositories.onboarding_repo import mark_onboarding_complete
from src.repositories.learning_repo import get_learning_repository
from src.rico_openai_runtime import call_openai_minimal
from src.rico_env import get_ai_provider
import src.services.chat_service as chat_service
from src.rico_openai_agent import RicoOpenAIAgent
from src.agent.responses.schema import build_error_response

logger = logging.getLogger(__name__)
_UTC = timezone.utc

# Constants
_UNSAFE_CHARS_RE = re.compile(r"[<>\"']")
_PDF_MAGIC = b"%PDF"
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_PUBLIC_USER_ID_RE = re.compile(r"^public:web-[a-z0-9-]{8,80}$", re.I)
_SAFE_SESSION_RE = re.compile(r"^[a-zA-Z0-9\-_]+$")

router = APIRouter(prefix="/api/v1/rico", tags=["rico"])


# ============================================================================
# Pydantic Models
# ============================================================================

class RicoChatRequest(BaseModel):
    """Authenticated chat request - user_id derived from JWT."""
    message: str = Field(..., max_length=4096)

    @validator("message")
    def non_empty_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class RicoPublicChatRequest(BaseModel):
    """Public chat request with session tracking."""
    message: str = Field(..., max_length=2048)
    session_id: str = Field(..., min_length=8, max_length=64)

    @validator("session_id")
    def safe_session_id(cls, v: str) -> str:
        if not _SAFE_SESSION_RE.match(v):
            raise ValueError("Session ID must be alphanumeric, hyphen, or underscore")
        return v

    @validator("message")
    def non_empty_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class PublicChatResponse(BaseModel):
    """Typed response for public chat endpoint."""
    message: str
    type: str = "response"
    matches: list[dict[str, Any]] | None = None
    options: list[dict[str, Any]] | None = None
    next_action: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "message": "I found 3 software engineer positions in Dubai",
                "type": "response",
                "matches": [{"title": "Senior Engineer", "company": "Tech Corp"}],
                "options": None,
                "next_action": None
            }
        }


class SavedSearchRequest(BaseModel):
    """Request to save a search query."""
    query: str = Field(..., min_length=1, max_length=500)
    filters: dict[str, Any] = Field(default_factory=dict)

    @validator("query")
    def non_empty_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")
        return v.strip()


class SavedSearchResponse(BaseModel):
    """Response for saved search operations."""
    id: str | None = None
    query: str
    filters: dict[str, Any]
    created_at: str | None = None
    status: str = "saved"


class FeedbackRequest(BaseModel):
    """Feedback on job matches."""
    job_id: str = Field(..., min_length=1, max_length=100)
    feedback_type: str = Field(..., pattern="^(positive|negative|neutral)$")
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=500)


class ProfileResponse(BaseModel):
    """Typed profile response."""
    profile_exists: bool
    email: str | None = None
    target_roles: list[str] | None = None
    preferred_cities: list[str] | None = None
    skills: list[str] | None = None
    years_experience: float | None = None
    completeness_score: float | None = None


class MetricsResponse(BaseModel):
    """Prometheus-style metrics response."""
    uptime_seconds: float
    total_requests: int
    avg_response_time_ms: float
    active_sessions: int
    cache_hit_rate: float
    timestamp: str


# ============================================================================
# Helper Functions
# ============================================================================

def _safe_filename(name: str | None) -> str:
    """Strip path traversal and unsafe chars from an uploaded filename."""
    if not name:
        return "upload"
    name = os.path.basename(name)
    name = _UNSAFE_CHARS_RE.sub("", name)
    return name.strip() or "upload"


def _is_valid_public_user_id(value: str) -> bool:
    """Validate that a user_id matches the expected guest session format."""
    return bool(_PUBLIC_USER_ID_RE.fullmatch(value or ""))


def _resolve_upload_user_id(
    request: Request,
    query_user_id: str | None,
    form_user_id: str | None,
) -> str:
    """Resolve user ID for CV upload, allowing authenticated or validated public sessions."""
    try:
        return get_current_user_id(request)
    except HTTPException:
        pass

    user_id = (query_user_id or form_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id is required")

    if not _is_valid_public_user_id(user_id):
        raise HTTPException(
            status_code=401,
            detail="Authentication or valid public session required"
        )

    return user_id


def _validate_jotform_secret(request: Request) -> None:
    """Reject requests when JOTFORM_WEBHOOK_SECRET is configured but not matched."""
    webhook_secret = os.getenv("JOTFORM_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        return

    provided = (
        request.headers.get("X-Jotform-Signature")
        or request.headers.get("X-Webhook-Secret")
        or request.query_params.get("secret", "")
    )
    if not provided or not secrets.compare_digest(provided, webhook_secret):
        logger.warning("jotform_webhook: missing or invalid secret")
        raise HTTPException(status_code=403, detail="Invalid or missing webhook secret")


def _extract_roles_from_cv_text(cv_text: str) -> list[str]:
    """Extract job titles from CV text using role patterns."""
    if not cv_text:
        return []

    roles = set()
    text_lower = cv_text.lower()

    # Pattern 1: Common role title patterns (Senior X, X Manager, etc.)
    role_patterns = [
        r"(?:senior|lead|principal|staff|junior|mid)?\s*(?:manager|engineer|developer|architect|analyst|consultant|specialist|director|coordinator|officer)",
        r"(?:operations|environmental|hse|qhse|ehs|safety|quality|compliance|sustainability)\s*(?:manager|lead|officer|specialist|coordinator)",
    ]

    for pattern in role_patterns:
        matches = re.finditer(pattern, text_lower, re.IGNORECASE)
        for match in matches:
            role = match.group(0).strip().title()
            if len(role.split()) <= 4:  # Reasonable role length
                roles.add(role)

    # Pattern 2: Extract from experience section lines
    lines = cv_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue

        # Look for lines that look like job titles (capitalized, no numbers at start)
        if re.match(r'^[A-Z][A-Za-z\s&/+-]{3,50}$', line):
            # Filter out common non-role lines
            skip_keywords = {'summary', 'experience', 'education', 'skills', 'certifications', 'languages', 'contact', 'profile'}
            words = line.lower().split()
            if not any(word in skip_keywords for word in words):
                roles.add(line.strip())

    return sorted(list(roles))[:5]  # Return top 5 roles


def _webhook_handler(event_name: str):
    """Decorator to standardize webhook error handling."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                logger.exception(f"{event_name}_webhook_error: {e}")
                return {"ok": True, "status": "accepted", "message": "Webhook received, processing error logged"}
        return wrapper
    return decorator


def _strip_internal_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Strip internal debug fields from responses to prevent leakage."""
    internal_fields = {
        "internal_debug", "raw_prompt", "system_prompt", "full_context",
        "debug_info", "internal_state", "agent_trace", "llm_trace"
    }
    return {k: v for k, v in data.items() if k not in internal_fields}


# ============================================================================
# Metrics (simple in-memory, replace with Prometheus in production)
# ============================================================================

class MetricsCollector:
    """Simple metrics collector - replace with Prometheus in production."""
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.total_response_time = 0.0
        self.cache_hits = 0
        self.cache_misses = 0

    def record_request(self, duration_ms: float):
        self.request_count += 1
        self.total_response_time += duration_ms

    def record_cache_hit(self):
        self.cache_hits += 1

    def record_cache_miss(self):
        self.cache_misses += 1

    @property
    def avg_response_time_ms(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_response_time / self.request_count

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time

_metrics = MetricsCollector()


# ============================================================================
# Profile Endpoints
# ============================================================================

@router.get("/profile", response_model=ProfileResponse)
def rico_get_profile(request: Request) -> ProfileResponse:
    """Get user profile with completeness score."""
    start_time = time.time()
    user = get_current_user(request)
    user_id = user["email"]

    profile = get_profile(user_id)

    if profile is None:
        _metrics.record_request((time.time() - start_time) * 1000)
        return ProfileResponse(profile_exists=False, email=user_id)

    # Calculate completeness (simplified - use resolver for full)
    from src.agent.context.resolver import resolve_profile_context
    context = resolve_profile_context(user_id)

    response = ProfileResponse(
        profile_exists=True,
        email=user_id,
        target_roles=getattr(profile, "target_roles", None),
        preferred_cities=getattr(profile, "preferred_cities", None),
        skills=getattr(profile, "skills", None),
        years_experience=getattr(profile, "years_experience", None),
        completeness_score=context.completeness_score,
    )

    _metrics.record_request((time.time() - start_time) * 1000)
    return response


# ============================================================================
# Saved Search Endpoints
# ============================================================================

@router.get("/settings/saved-searches")
def rico_list_saved_searches(request: Request) -> dict[str, Any]:
    """List all saved searches for the authenticated user."""
    start_time = time.time()
    user = get_current_user(request)
    user_id = user["email"]

    rows = list_saved_searches(user_id)
    searches = []
    for row in rows:
        r = dict(row)
        if "created_at" in r and hasattr(r["created_at"], "isoformat"):
            r["created_at"] = r["created_at"].isoformat()
        searches.append(r)

    _metrics.record_request((time.time() - start_time) * 1000)
    return {"searches": searches, "total": len(searches)}


@router.post("/settings/saved-searches", status_code=201, response_model=SavedSearchResponse)
def rico_create_saved_search(request: Request, body: SavedSearchRequest) -> SavedSearchResponse:
    """Save a new search query."""
    start_time = time.time()
    user = get_current_user(request)
    user_id = user["email"]

    search_id = save_search(user_id, body.query, body.filters)

    _metrics.record_request((time.time() - start_time) * 1000)
    return SavedSearchResponse(
        id=search_id,
        query=body.query,
        filters=body.filters,
        status="saved"
    )


@router.delete("/settings/saved-searches/{search_id}", status_code=204)
def rico_delete_saved_search(request: Request, search_id: str) -> None:
    """Delete a saved search by ID."""
    start_time = time.time()
    user = get_current_user(request)
    user_id = user["email"]

    deleted = delete_search(user_id, search_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved search not found")

    _metrics.record_request((time.time() - start_time) * 1000)


# ============================================================================
# Chat Endpoints
# ============================================================================

@router.post("/chat")
@limiter.limit(LIMIT_CHAT)
def rico_chat(request: Request, payload: RicoChatRequest) -> dict[str, Any]:
    """Authenticated chat endpoint."""
    start_time = time.time()
    try:
        user = get_current_user(request)
        user_id = user["email"]

        result = chat_service.send_message(user_id=user_id, message=payload.message)

        _metrics.record_request((time.time() - start_time) * 1000)
        return result
    except Exception as exc:
        _metrics.record_request((time.time() - start_time) * 1000)
        return build_error_response(
            "I encountered an error processing your request. Please try again.",
            log_exc=exc,
            user_id=user_id if "user_id" in locals() else "unknown",
        )


@router.post("/chat/public", response_model=PublicChatResponse)
@limiter.limit("10/minute")
def rico_chat_public(request: Request, payload: RicoPublicChatRequest) -> PublicChatResponse:
    """Unauthenticated chat for landing page visitors."""
    start_time = time.time()

    try:
        # Sanitize session_id (already validated by Pydantic)
        safe_sid = payload.session_id[:64]
        user_id = f"public:{safe_sid}"

        result = chat_service.send_message(user_id=user_id, message=payload.message)

        # Strip internal diagnostics from unauthenticated responses
        stripped_result = _strip_internal_fields(result)

        response = PublicChatResponse(
            message=stripped_result.get("message", ""),
            type=stripped_result.get("type", "response"),
            matches=stripped_result.get("matches"),
            options=stripped_result.get("options"),
            next_action=stripped_result.get("next_action"),
        )

        _metrics.record_request((time.time() - start_time) * 1000)
        return response
    except Exception as exc:
        _metrics.record_request((time.time() - start_time) * 1000)
        err = build_error_response(
            "I encountered an error processing your request. Please try again.",
            log_exc=exc,
            user_id=f"public:{payload.session_id[:16]}",
        )
        return PublicChatResponse(
            message=err["message"],
            type="error",
            matches=None,
            options=None,
            next_action=err.get("debug_id"),
        )


@router.get("/chat/history")
@limiter.limit(LIMIT_CHAT)
def rico_chat_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = None,
) -> dict[str, Any]:
    """Get conversation history with pagination."""
    start_time = time.time()
    user = get_current_user(request)
    user_id = user["email"]

    before_ts = None
    if before:
        try:
            before_ts = datetime.fromisoformat(before.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid timestamp format")

    history = chat_service.get_chat_history(user_id, limit=limit, before=before_ts)

    _metrics.record_request((time.time() - start_time) * 1000)
    return {
        "messages": history,
        "total": len(history),
        "has_more": len(history) == limit,
    }


# ============================================================================
# Feedback Endpoint
# ============================================================================

@router.post("/feedback", status_code=204)
def rico_feedback(request: Request, body: FeedbackRequest) -> None:
    """Record user feedback on job matches for learning."""
    start_time = time.time()
    user = get_current_user(request)
    user_id = user["email"]

    # Map rating to weight for learning
    weight_map = {1: -0.5, 2: -0.2, 3: 0.0, 4: 0.3, 5: 0.7}
    weight = weight_map.get(body.rating, 0.0)

    # Record in learning repository
    learning_repo = get_learning_repository()
    learning_repo.record_signal(
        canonical_user_id=user_id,
        signal_type="feedback",
        signal_value=body.feedback_type,
        signal_weight=weight,
        source="user_feedback",
        metadata={
            "job_id": body.job_id,
            "rating": body.rating,
            "comment": body.comment,
        }
    )

    _metrics.record_request((time.time() - start_time) * 1000)


# ============================================================================
# AI Probe Endpoint
# ============================================================================

@router.get("/openai-smoke")
@limiter.limit(LIMIT_CHAT)
def rico_openai_smoke(request: Request) -> dict[str, Any]:
    """Minimal premium-provider runtime probe."""
    start_time = time.time()
    get_current_user(request)

    provider = get_ai_provider()
    agent = RicoOpenAIAgent()

    if provider not in ("openai", "deepseek"):
        _metrics.record_request((time.time() - start_time) * 1000)
        return {
            "success": False,
            "provider": provider,
            "provider_available": agent.provider_available,
            "openai_available": False,
            "deepseek_available": agent.deepseek_available,
            "hf_available": agent.hf_available,
            "response": (
                f"Premium AI provider disabled (active provider: {provider}). "
                "Set RICO_AI_PROVIDER=openai or RICO_AI_PROVIDER=deepseek to enable advanced reasoning."
            ),
            "error": "OpenAIProviderDisabled",
            "error_detail": None,
            "model": None,
            "fallback_model": None,
        }

    if provider == "openai":
        result = call_openai_minimal("Say OK", smoke=True)
    else:
        result = call_openai_minimal("Say OK", smoke=True, provider=provider)

    _metrics.record_request((time.time() - start_time) * 1000)
    return {
        "success": result.get("success", False),
        "provider": provider,
        "provider_available": result.get("provider_available"),
        "model": (
            result.get("model")
            or result.get("deepseek_model")
            or result.get("openai_model")
        ),
        "fallback_model": result.get("fallback_model"),
        "response": result.get("text"),
        "error": result.get("error"),
        "error_detail": result.get("error_detail"),
        "openai_available": result.get(
            "openai_available",
            bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API")),
        ),
        "deepseek_available": result.get(
            "deepseek_available",
            bool(os.getenv("DEEPSEEK_API_KEY")),
        ),
    }


# ============================================================================
# AI Provider Health Endpoint
# ============================================================================

@router.get("/health/ai-provider")
def rico_ai_provider_health(request: Request) -> dict[str, Any]:
    """Health check endpoint exposing current AI provider availability and state."""
    from src.rico_openai_agent import RicoOpenAIAgent
    from src.rico_env import get_ai_provider

    provider = get_ai_provider()
    agent = RicoOpenAIAgent()

    return {
        "active_provider": provider,
        "provider_available": agent.provider_available,
        "openai_available": agent.openai_available,
        "deepseek_available": agent.deepseek_available,
        "hf_available": agent.hf_available,
        "provider_state": "available" if agent.provider_available else "unavailable",
        "timestamp": datetime.now(_UTC).isoformat(),
    }


# ============================================================================
# Metrics Endpoint
# ============================================================================

@router.get("/metrics", response_model=MetricsResponse)
def rico_metrics(request: Request) -> MetricsResponse:
    """Prometheus-style metrics endpoint."""
    # Require authentication for metrics
    get_current_user(request)

    return MetricsResponse(
        uptime_seconds=_metrics.uptime_seconds,
        total_requests=_metrics.request_count,
        avg_response_time_ms=_metrics.avg_response_time_ms,
        active_sessions=0,  # Would need session tracking with HyperLogLog
        cache_hit_rate=_metrics.cache_hit_rate,
        timestamp=datetime.now(_UTC).isoformat(),
    )


# ============================================================================
# CV Upload Endpoint
# ============================================================================

@router.post("/upload-cv")
@limiter.limit(LIMIT_UPLOAD)
async def rico_upload_cv(
    request: Request,
    file: UploadFile = File(...),
    user_id: str | None = None,
    form_user_id: str | None = Form(None, alias="user_id"),
) -> dict[str, Any]:
    """Upload and parse CV file (PDF only)."""
    start_time = time.time()
    resolved_user_id = _resolve_upload_user_id(request, user_id, form_user_id)

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    if not data.startswith(_PDF_MAGIC):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted")

    safe_name = _safe_filename(file.filename)
    parsed = chat_service.parse_cv(data, filename=safe_name)

    # Persist extracted CV fields to profile
    existing_profile = get_profile(resolved_user_id)
    existing_skills = getattr(existing_profile, "skills", []) if existing_profile else []

    # Extract target roles from CV text using role patterns
    cv_text = parsed.get("text", "")
    target_roles = _extract_roles_from_cv_text(cv_text)

    profile_updates = {
        "email": parsed.get("emails", [None])[0] if parsed.get("emails") else None,
        "phone": parsed.get("phones", [None])[0] if parsed.get("phones") else None,
        "skills": parsed.get("skills", []) if parsed.get("skills") else existing_skills,
        "years_experience": parsed.get("years_experience_hint"),
        "target_roles": target_roles if target_roles else None,
        "cv_filename": safe_name,
        "cv_status": "parsed",
        "cv_extracted_at": datetime.now(_UTC).isoformat(),
        "profile_creation_mode": "cv_first",
        "manual_profile_wizard_disabled": True,
    }

    profile_updates = {k: v for k, v in profile_updates.items() if v not in (None, [], {})}
    upsert_profile(user_id=resolved_user_id, updates=profile_updates)
    mark_onboarding_complete(resolved_user_id)

    _metrics.record_request((time.time() - start_time) * 1000)
    return {
        "user_id": resolved_user_id,
        "filename": safe_name,
        "parsed": parsed,
    }


# ============================================================================
# Webhook Endpoints
# ============================================================================

@router.post("/webhooks/telegram")
@limiter.limit(LIMIT_WEBHOOK)
@_webhook_handler("telegram")
async def rico_telegram_webhook(request: Request) -> dict[str, Any]:
    """Telegram bot webhook endpoint."""
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}  # Bad JSON - always ACK
    return chat_service.handle_telegram_update(update)


@router.post("/webhooks/jotform")
@limiter.limit(LIMIT_WEBHOOK)
@_webhook_handler("jotform")
async def rico_jotform_webhook(request: Request) -> dict[str, Any]:
    """Jotform onboarding webhook endpoint."""
    _validate_jotform_secret(request)
    try:
        payload = await request.json()
    except Exception:
        logger.warning("jotform_webhook: invalid JSON body")
        return {"status": "accepted", "message": "Webhook received"}
    return chat_service.handle_jotform_submission(payload)


@router.post("/webhooks/github")
@limiter.limit(LIMIT_WEBHOOK)
@_webhook_handler("github")
async def rico_github_webhook(request: Request) -> dict[str, Any]:
    """GitHub webhook endpoint (push, PR, issues, ping)."""
    raw_body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()

    if secret:
        expected = "sha256=" + hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not sig or not hmac.compare_digest(sig, expected):
            logger.warning("github_webhook: invalid signature")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event", "")
    if not event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except Exception:
        logger.warning("github_webhook: invalid JSON body")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    return chat_service.handle_github_event(event, payload)
