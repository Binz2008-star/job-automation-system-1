"""
src/models/action_log.py
Domain model for a single agent action execution record.
"""
from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class ActionLog(TypedDict, total=False):
    action_id: str            # deterministic hash (SHA-256[:12] of type:link)
    action_type: str          # apply | skip | save | block | trigger_pipeline
    user_email: str
    job_id: Optional[str]
    job_title: Optional[str]
    job_company: Optional[str]
    timestamp: str            # ISO-8601 UTC
    result_status: str        # success | failure | duplicate
    result_message: str
    duration_ms: int
    failure_reason: Optional[str]
