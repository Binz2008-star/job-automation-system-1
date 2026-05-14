from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    include_keywords: List[str]
    exclude_keywords: List[str]
    min_score: int
    max_daily_applies: int
    telegram_chat_id: str
    score_threshold_apply: int
    score_threshold_watch: int

    model_config = {"extra": "allow"}


class SettingsUpdateRequest(BaseModel):
    include_keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    min_score: Optional[int] = None
    max_daily_applies: Optional[int] = None
    telegram_chat_id: Optional[str] = None
    score_threshold_apply: Optional[int] = None
    score_threshold_watch: Optional[int] = None
