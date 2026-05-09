from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PipelineStatusResponse(BaseModel):
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    jobs_found: int = 0
    error: Optional[str] = None
    run_id: Optional[int] = None

    model_config = {"extra": "allow"}


class PipelineTriggerResponse(BaseModel):
    status: str
    message: str
