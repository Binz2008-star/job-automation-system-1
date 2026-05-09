"""
src/services/settings_service.py
Business logic for reading and updating settings.
All persistence is delegated to repositories.settings_repo.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from src.db import is_db_available
from src.repositories import settings_repo

_DEFAULTS: Dict[str, Any] = {
    "include_keywords": [],
    "exclude_keywords": [],
    "min_score": 50,
    "max_daily_applies": 10,
    "telegram_chat_id": "",
    "score_threshold_apply": 75,
    "score_threshold_watch": 50,
}

_ALLOWED_KEYS = frozenset(_DEFAULTS)


def get_settings() -> Dict[str, Any]:
    """Effective settings: env-var defaults overridden by DB row."""
    base = dict(_DEFAULTS)
    base["exclude_keywords"] = _parse_csv(os.getenv("EXCLUDE_KEYWORDS", ""))
    base["telegram_chat_id"] = os.getenv("TELEGRAM_CHAT_ID", "")

    if is_db_available():
        db_row = settings_repo.read()
        if db_row:
            base.update(db_row)

    return base


def update_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a subset of settings. Unknown keys are silently dropped.
    Returns the new full effective settings dict.
    """
    clean = {k: v for k, v in data.items() if k in _ALLOWED_KEYS}

    if is_db_available():
        settings_repo.upsert(clean)

    if "exclude_keywords" in clean:
        os.environ["EXCLUDE_KEYWORDS"] = ",".join(str(k) for k in clean["exclude_keywords"])

    return get_settings()


def _parse_csv(value: str) -> List[str]:
    return [k.strip() for k in value.split(",") if k.strip()]
