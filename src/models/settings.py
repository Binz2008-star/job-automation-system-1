"""
src/models/settings.py
Domain model for user-configurable settings.
"""
from __future__ import annotations

from typing import List
from typing_extensions import TypedDict


class Settings(TypedDict):
    include_keywords: List[str]
    exclude_keywords: List[str]
    min_score: int
    max_daily_applies: int
    telegram_chat_id: str
    score_threshold_apply: int
    score_threshold_watch: int
