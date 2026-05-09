"""
src/schemas/actions.py
HTTP contracts for POST /api/v1/actions/run.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.agent.orchestrator.intent_detector import VALID_ACTION_TYPES

_VALID = sorted(VALID_ACTION_TYPES)


class ActionRequest(BaseModel):
    action: str = Field(
        ...,
        description=f"One of: {', '.join(_VALID)}",
    )
    job_key: str = Field(
        "",
        max_length=256,
        description="Hex fingerprint from get_job_id() — used to look up cached job when 'job' is omitted",
    )
    job: Optional[Dict[str, Any]] = Field(
        None,
        description="Full job dict. If omitted, resolved from Telegram job cache via job_key.",
    )
    source: str = Field(
        "api",
        max_length=64,
        description="Caller label for audit logs",
    )
    dry_run: bool = Field(
        False,
        description="When true: log intent only, skip execution and audit",
    )


class ActionResponse(BaseModel):
    ok: bool
    message: str
    action: str
    job_key: str
    source: str
    user_id: str
    dry_run: bool
    data: Dict[str, Any]
    error: Optional[str]
    confidence: float
    explanation: str
    duration_ms: int
