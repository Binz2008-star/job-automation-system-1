"""
src/api/routers/rico_chat.py
HTTP adapters that expose Rico AI flows through the layered API.
Rico internals are not modified — this is a pure routing shim.

Routes:
  POST /api/v1/rico/chat                        natural-language chat  (JWT required)
  GET  /api/v1/rico/profile                     user profile           (JWT required)
  GET  /api/v1/rico/settings/saved-searches     list saved searches    (JWT required)
  POST /api/v1/rico/settings/saved-searches     save a search          (JWT required)
  POST /api/v1/rico/upload-cv                   CV file upload + parsing
  POST /api/v1/rico/webhooks/telegram           Telegram bot webhook (called by Telegram)
  POST /api/v1/rico/webhooks/jotform            Jotform onboarding webhook (called by Jotform)
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from typing import Any, Dict

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

import src.services.chat_service as chat_service
from src.api.deps import get_current_user
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


class RicoChatRequest(BaseModel):
    # user_id intentionally absent — derived from the authenticated JWT cookie.
    # Any user_id field sent in the body is ignored.
    message: str = Field(..., max_length=4096)


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


@router.post("/upload-cv")
@limiter.limit(LIMIT_UPLOAD)
async def rico_upload_cv(request: Request, user_id: str, file: UploadFile = File(...)) -> Dict[str, Any]:
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
        "user_id": user_id,
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
