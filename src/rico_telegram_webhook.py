"""Telegram webhook controller for Rico AI."""

from __future__ import annotations

from typing import Any, Dict

from src.rico_chat_api import RicoChatAPI

chat_api = RicoChatAPI()


def process_telegram_update(update: Dict[str, Any]) -> Dict[str, Any]:
    message = update.get("message", {})
    chat = message.get("chat", {})
    user = message.get("from", {})

    text = message.get("text", "")
    user_id = str(chat.get("id") or user.get("id") or "telegram-user")

    response = chat_api.process_message(user_id=user_id, message=text)

    return {
        "chat_id": user_id,
        "reply": response,
    }
