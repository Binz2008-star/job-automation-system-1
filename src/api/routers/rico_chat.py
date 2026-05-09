"""
src/api/routers/rico_chat.py
HTTP adapters that expose Rico AI flows through the layered API.
Rico internals are not modified — this is a pure routing shim.

Routes (all public — no JWT required, consistent with Rico's original design):
  POST /api/v1/rico/chat              natural-language chat
  POST /api/v1/rico/upload-cv         CV file upload + parsing
  POST /api/v1/rico/webhooks/telegram Telegram bot webhook (called by Telegram)
  POST /api/v1/rico/webhooks/jotform  Jotform onboarding webhook (called by Jotform)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

import src.services.chat_service as chat_service
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


class RicoChatRequest(BaseModel):
    user_id: str
    message: str = Field(..., max_length=4096)


@router.post("/chat")
@limiter.limit(LIMIT_CHAT)
def rico_chat(request: Request, payload: RicoChatRequest) -> Dict[str, Any]:
    return chat_service.send_message(user_id=payload.user_id, message=payload.message)


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
