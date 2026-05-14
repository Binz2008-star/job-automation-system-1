from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApplicationListResponse(BaseModel):
    applications: List[Dict[str, Any]]
    total: int
    page: int
    limit: int
    pages: int


class StatusUpdateRequest(BaseModel):
    status: str = Field(..., min_length=1)
    notes: Optional[str] = None


class StatusUpdateResponse(BaseModel):
    status: str
    job_id: str
    message: str
