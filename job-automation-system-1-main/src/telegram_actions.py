"""
src/telegram_actions.py
Telegram inline keyboard builder and API helpers.
Callback format: rico:<action>:<job_key>
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def build_job_keyboard(job: Dict[str, Any]) -> Dict[str, Any]:
    """Inline keyboard for a job card using the rico:action:key callback format."""
    from src.applications import get_job_id
    job_key = get_job_id(job)
    link = job.get("link", "")

    buttons: List[List[Dict[str, str]]] = []
    if link and link.startswith("http"):
        buttons.append([{"text": "Open / Apply", "url": link}])
    buttons.append([
        {"text": "Apply",  "callback_data": f"rico:apply:{job_key}"},
        {"text": "Save",   "callback_data": f"rico:save:{job_key}"},
        {"text": "Skip",   "callback_data": f"rico:skip:{job_key}"},
    ])
    buttons.append([
        {"text": "Why this?",    "callback_data": f"rico:why:{job_key}"},
        {"text": "Draft",        "callback_data": f"rico:draft:{job_key}"},
        {"text": "Not relevant", "callback_data": f"rico:not_relevant:{job_key}"},
    ])
    return {"inline_keyboard": buttons}


def answer_callback_query(callback_id: str, text: str = "") -> bool:
    """
    Acknowledge a Telegram callback query.
    Must be called within 10 s of the button press or Telegram shows a timeout.
    """
    token = _token()
    if not token or not callback_id:
        return False
    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token, method="answerCallbackQuery"),
            json={"callback_query_id": callback_id, "text": (text or "")[:200]},
            timeout=5,
        )
        return resp.ok
    except Exception as exc:
        logger.warning("answer_callback_query_failed: %s", exc)
        return False


def send_job_action(
    job: Dict[str, Any],
    decision: Optional[str] = None,
    reasoning: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """Send a single job card with inline action buttons."""
    token = _token()
    target = chat_id or _chat_id()
    if not token or not target:
        return False

    title = job.get("title", "N/A")
    company = job.get("company", "N/A")
    score = job.get("score", job.get("final_score", "N/A"))
    text = f"<b>{title}</b>\n🏢 {company}\n⭐ Score: {score}"
    if decision:
        text += f"\n🤖 Decision: <b>{decision}</b>"
    if reasoning:
        text += f"\nReason: {reasoning[:500]}"

    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token, method="sendMessage"),
            json={
                "chat_id": target,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": build_job_keyboard(job),
            },
            timeout=15,
        )
        return resp.ok
    except Exception as exc:
        logger.warning("send_job_action_failed: %s", exc)
        return False
