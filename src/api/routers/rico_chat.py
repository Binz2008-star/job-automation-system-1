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
from typing import Any, Dict

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel

import src.services.chat_service as chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rico", tags=["rico"])


class RicoChatRequest(BaseModel):
    user_id: str
    message: str


@router.post("/chat")
def rico_chat(payload: RicoChatRequest) -> Dict[str, Any]:
    return chat_service.send_message(user_id=payload.user_id, message=payload.message)


@router.post("/upload-cv")
async def rico_upload_cv(user_id: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    data = await file.read()
    parsed = chat_service.parse_cv(data, filename=file.filename or "cv.pdf")
    return {
        "user_id": user_id,
        "filename": file.filename,
        "parsed": parsed,
    }


@router.post("/webhooks/telegram")
async def rico_telegram_webhook(request: Request) -> Dict[str, Any]:
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}  # always ack — bad JSON should not trigger Telegram retries
    try:
        return chat_service.handle_telegram_update(update)
    except Exception as exc:
        # Log but always return 200 so Telegram does not retry the delivery.
        logger.warning("telegram_webhook_error: %s", exc)
        return {"ok": True}


@router.post("/webhooks/jotform")
async def rico_jotform_webhook(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    return chat_service.handle_jotform_submission(payload)
