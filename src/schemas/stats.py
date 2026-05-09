from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


class StatsResponse(BaseModel):
    total_applied: int
    status_breakdown: Dict[str, int]
    interviews_scheduled: int
    rejections: int
    pending: int
    success_rate: float

    model_config = {"extra": "allow"}
