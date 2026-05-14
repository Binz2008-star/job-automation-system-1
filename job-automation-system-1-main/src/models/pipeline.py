"""
src/models/pipeline.py
Domain model for a pipeline execution record.
"""
from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class PipelineRun(TypedDict, total=False):
    run_id: Optional[int]
    started_at: Optional[str]
    finished_at: Optional[str]
    status: str        # 'idle' | 'running' | 'done' | 'failed'
    jobs_found: int
    error: Optional[str]
