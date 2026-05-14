"""
src/api/routers/pipeline.py
Thin HTTP layer for pipeline status and manual trigger.
All state management lives in src.services.pipeline_service.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_current_user
from src.schemas.pipeline import PipelineStatusResponse, PipelineTriggerResponse
from src.services.pipeline_service import get_status, trigger

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


@router.get("/status", response_model=PipelineStatusResponse)
def pipeline_status(_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return get_status()


@router.post("/trigger", response_model=PipelineTriggerResponse)
def trigger_pipeline(_user: dict = Depends(get_current_user)) -> PipelineTriggerResponse:
    try:
        trigger()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return PipelineTriggerResponse(
        status="triggered",
        message="Pipeline started. Poll /api/v1/pipeline/status for progress.",
    )
