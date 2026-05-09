"""
src/services/chat_service.py
Thin service adapter for Rico AI chat, CV parsing, and webhook flows.
Does not modify Rico internals — delegates directly to existing Rico modules
via deferred imports to avoid eager loading of heavy dependencies.
"""
from __future__ import annotations

from typing import Any, Dict


def send_message(user_id: str, message: str) -> Dict[str, Any]:
    """Route a chat message through RicoChatAPI and return the response dict."""
    from src.rico_chat_api import RicoChatAPI
    return RicoChatAPI().process_message(user_id=user_id, message=message)


def parse_cv(data: bytes, filename: str = "cv.pdf") -> Dict[str, Any]:
    """Parse CV bytes and return structured ParsedCV dict via CVParser."""
    from src.cv_parser import CVParser
    return CVParser().parse_bytes(data, filename=filename).to_dict()


def handle_telegram_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch an incoming Telegram update to the Rico webhook handler."""
    from src.rico_telegram_webhook import process_telegram_update
    return process_telegram_update(update)


def handle_jotform_submission(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process a Jotform onboarding webhook payload via the Rico handler."""
    from src.rico_jotform_webhook import handle_jotform_submission as _handle
    return _handle(payload)
