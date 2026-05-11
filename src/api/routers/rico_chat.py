"""
src/api/routers/rico_chat.py
HTTP adapters that expose Rico AI flows through the layered API.
Rico internals are not modified — this is a pure routing shim.

Routes:
  POST /api/v1/rico/chat                        natural-language chat  (JWT required)
  GET  /api/v1/rico/profile                     user profile           (JWT required)
  GET  /api/v1/rico/settings/saved-searches     list saved searches    (JWT required)
  POST /api/v1/rico/settings/saved-searches     save a search          (JWT required)
  GET  /api/v1/rico/openai-smoke                OpenAI runtime probe   (JWT required)
  POST /api/v1/rico/upload-cv                   CV file upload + parsing
  POST /api/v1/rico/webhooks/telegram           Telegram bot webhook (called by Telegram)
  POST /api/v1/rico/webhooks/jotform            Jotform onboarding webhook (called by Jotform)
  POST /api/v1/rico/webhooks/github             GitHub webhook (push, PR, issues, ping)
  POST /api/v1/rico/chat/public                 Public chat (no JWT, session-based, rate-limited)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from typing import Any, Dict

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

import src.services.chat_service as chat_service
from src.api.deps import get_current_user, get_current_user_id
from src.api.rate_limit import LIMIT_CHAT, LIMIT_UPLOAD, LIMIT_WEBHOOK, limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rico", tags=["rico"])

_UNSAFE_CHARS_RE = re.compile(r"[<>\"']")
_PDF_MAGIC = b"%PDF"
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _safe_filename(name: str | None) -> str:
    """Strip path traversal and unsafe chars from an uploaded filename."""
    if not name:
        return "upload"
    name = os.path.basename(name)
    name = _UNSAFE_CHARS_RE.sub("", name)
    return name.strip() or "upload"


def _validate_jotform_secret(request: Request) -> None:
    """Reject requests when JOTFORM_WEBHOOK_SECRET is configured but not matched."""
    webhook_secret = os.getenv("JOTFORM_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        return  # not configured — allow (dev mode)
    provided = (
        request.headers.get("X-Jotform-Signature")
        or request.headers.get("X-Webhook-Secret")
        or request.query_params.get("secret", "")
    )
    if not provided or not secrets.compare_digest(provided, webhook_secret):
        logger.warning("jotform_webhook: missing or invalid secret")
        raise HTTPException(status_code=403, detail="Invalid or missing webhook secret")


def _resolve_upload_user_id(
    request: Request,
    query_user_id: str | None,
    form_user_id: str | None,
) -> str:
    """Prefer the authenticated user when present, otherwise accept legacy user_id inputs."""
    try:
        return get_current_user_id(request)
    except HTTPException:
        pass

    user_id = (query_user_id or form_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id is required")
    return user_id


class RicoChatRequest(BaseModel):
    # user_id intentionally absent — derived from the authenticated JWT cookie.
    # Any user_id field sent in the body is ignored.
    message: str = Field(..., max_length=4096)


class RicoPublicChatRequest(BaseModel):
    message: str = Field(..., max_length=2048)
    session_id: str = Field(..., min_length=8, max_length=64)


class SavedSearchRequest(BaseModel):
    query:   str            = Field(..., min_length=1, max_length=500)
    filters: Dict[str, Any] = Field(default_factory=dict)


@router.get("/profile")
def rico_get_profile(request: Request) -> Dict[str, Any]:
    user    = get_current_user(request)
    user_id = user["email"]
    from src.repositories.profile_repo import get_profile
    profile = get_profile(user_id)
    if profile is None:
        return {"profile_exists": False, "email": user_id}
    data = asdict(profile)
    data["profile_exists"] = True
    return data


@router.get("/settings/saved-searches")
def rico_list_saved_searches(request: Request) -> Dict[str, Any]:
    user    = get_current_user(request)
    user_id = user["email"]
    from src.repositories.profile_repo import list_saved_searches
    rows = list_saved_searches(user_id)
    searches = []
    for row in rows:
        r = dict(row)
        if "created_at" in r and hasattr(r["created_at"], "isoformat"):
            r["created_at"] = r["created_at"].isoformat()
        searches.append(r)
    return {"searches": searches, "total": len(searches)}


@router.post("/settings/saved-searches", status_code=201)
def rico_create_saved_search(request: Request, body: SavedSearchRequest) -> Dict[str, Any]:
    user    = get_current_user(request)
    user_id = user["email"]
    from src.repositories.profile_repo import save_search
    save_search(user_id, body.query, body.filters)
    return {"status": "saved", "query": body.query}


@router.post("/chat")
@limiter.limit(LIMIT_CHAT)
def rico_chat(request: Request, payload: RicoChatRequest) -> Dict[str, Any]:
    user = get_current_user(request)   # raises 401 if unauthenticated
    user_id = user["email"]            # trust the JWT, never the request body
    return chat_service.send_message(user_id=user_id, message=payload.message)


@router.post("/chat/public")
@limiter.limit("10/minute")
def rico_chat_public(request: Request, payload: RicoPublicChatRequest) -> Dict[str, Any]:
    """Unauthenticated chat for landing page visitors.

    Uses a client-supplied session_id (e.g. a UUID generated in the browser) as
    the user identity.  Prefixed with 'public:' so these sessions are isolated
    from real user accounts and never collide with JWT-authenticated user_ids.

    Jotform is the fallback for users who prefer a form-based onboarding flow.
    This endpoint is the primary entry point from the landing page.
    """
    # Sanitise the session_id — alphanumeric + hyphens only
    safe_sid = re.sub(r"[^a-zA-Z0-9\-_]", "", payload.session_id)[:64]
    if not safe_sid:
        raise HTTPException(status_code=422, detail="Invalid session_id")
    user_id = f"public:{safe_sid}"
    result = chat_service.send_message(user_id=user_id, message=payload.message)
    # Strip internal diagnostics from unauthenticated responses
    return {
        "message": result.get("message", ""),
        "type": result.get("type", "response"),
        "matches": result.get("matches"),
        "options": result.get("options"),
        "next_action": result.get("next_action"),
    }


@router.get("/openai-smoke")
@limiter.limit(LIMIT_CHAT)
def rico_openai_smoke(request: Request) -> Dict[str, Any]:
    """Minimal OpenAI runtime probe.

    Sends "Say OK" through the same minimal Responses API path used by chat,
    so a green smoke means the prod OpenAI integration is healthy. Never
    leaks the API key or full profile data — only the structured error.
    """
    get_current_user(request)  # raises 401 if unauthenticated
    from src.rico_env import get_ai_provider

    provider = get_ai_provider()

    if provider in ("none", "huggingface"):
        # OpenAI is not the active provider — skip the live API call
        from src.rico_openai_agent import RicoOpenAIAgent

        agent = RicoOpenAIAgent()
        return {
            "success": False,
            "provider": provider,
            "openai_available": False,
            "hf_available": agent.hf_available,
            "response": f"OpenAI provider disabled (active provider: {provider}). Set RICO_AI_PROVIDER=openai when API credits are available.",
            "error": "OpenAIProviderDisabled",
            "error_detail": None,
            "model": None,
            "fallback_model": None,
        }

    # OpenAI mode - use existing behavior
    from src.rico_openai_runtime import call_openai_minimal

    result = call_openai_minimal("Say OK", smoke=True)
    return {
        "success": result.get("success", False),
        "model": result.get("model") or result.get("openai_model"),
        "fallback_model": result.get("fallback_model"),
        "response": result.get("text"),
        "error": result.get("error"),
        "error_detail": result.get("error_detail"),
        "openai_available": result.get(
            "openai_available",
            bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API")),
        ),
    }


@router.post("/upload-cv")
@limiter.limit(LIMIT_UPLOAD)
async def rico_upload_cv(
    request: Request,
    file: UploadFile = File(...),
    user_id: str | None = None,
    form_user_id: str | None = Form(None, alias="user_id"),
) -> Dict[str, Any]:
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
    return {
        "user_id": resolved_user_id,
        "filename": safe_name,
        "parsed": parsed,
    }


@router.post("/webhooks/telegram")
@limiter.limit(LIMIT_WEBHOOK)
async def rico_telegram_webhook(request: Request) -> Dict[str, Any]:
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}  # always ack — bad JSON should not trigger Telegram retries
    try:
        return chat_service.handle_telegram_update(update)
    except Exception as exc:
        logger.warning("telegram_webhook_error: %s", exc)
        return {"ok": True}


@router.post("/webhooks/jotform")
@limiter.limit(LIMIT_WEBHOOK)
async def rico_jotform_webhook(request: Request) -> Dict[str, Any]:
    _validate_jotform_secret(request)
    try:
        payload = await request.json()
    except Exception:
        logger.warning("jotform_webhook: invalid JSON body")
        return {"status": "accepted", "message": "Webhook received"}
    try:
        return chat_service.handle_jotform_submission(payload)
    except Exception as exc:
        logger.warning("jotform_webhook_error: %s: %s", type(exc).__name__, exc)
        return {"status": "accepted", "message": "Webhook received, processing error logged"}


@router.post("/webhooks/github")
@limiter.limit(LIMIT_WEBHOOK)
async def rico_github_webhook(request: Request) -> Dict[str, Any]:
    raw_body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()
    if secret:
        expected = "sha256=" + hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not sig or not hmac.compare_digest(sig, expected):
            logger.warning("github_webhook: invalid or missing X-Hub-Signature-256")
            raise HTTPException(status_code=403, detail="Invalid or missing GitHub webhook signature")
    event = request.headers.get("X-GitHub-Event", "")
    if not event:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")
    try:
        import json as _json
        payload = _json.loads(raw_body) if raw_body else {}
    except Exception:
        logger.warning("github_webhook: invalid JSON body")
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        return chat_service.handle_github_event(event, payload)
    except Exception as exc:
        logger.warning("github_webhook_error: %s: %s", type(exc).__name__, exc)
        return {"status": "accepted", "message": "Webhook received, processing error logged"}
