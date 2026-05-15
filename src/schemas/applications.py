from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApplicationListResponse(BaseModel):
    applications: List[Dict[str, Any]]
    total: int
    page: int
    limit: int
    pages: int


class ApplicationCreateRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    location: str = ""
    url: str = ""
    status: str = Field(default="opened")
    source: str = Field(default="manual")


class ManualApplicationCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    location: str = ""
    url: str = ""
    status: str = Field(default="applied")


class StatusUpdateRequest(BaseModel):
    status: str = Field(..., min_length=1)
    notes: Optional[str] = None


class StatusUpdateResponse(BaseModel):
    status: str
    job_id: str
    message: str
