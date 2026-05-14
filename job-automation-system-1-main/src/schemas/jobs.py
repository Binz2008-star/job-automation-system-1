from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobListResponse(BaseModel):
    jobs: List[Dict[str, Any]]
    total: int
    page: int
    limit: int
    pages: int


class JobActionRequest(BaseModel):
    job: Dict[str, Any]


class JobActionResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
