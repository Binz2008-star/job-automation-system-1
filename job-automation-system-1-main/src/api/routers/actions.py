"""
src/api/routers/actions.py
POST /api/v1/actions/run — single dispatch point for all Rico job actions.

All surfaces (dashboard, mobile, future integrations) call this endpoint
instead of implementing their own logic. The runtime handles validation,
idempotency, tool execution, and audit logging.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.agent.runtime import agent_runtime
from src.api.deps import get_current_user
from src.api.rate_limit import LIMIT_CHAT, limiter
from src.schemas.actions import ActionRequest, ActionResponse

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])

LIMIT_ACTIONS = LIMIT_CHAT  # 30/minute — same as chat


@router.post("/run", response_model=ActionResponse)
@limiter.limit(LIMIT_ACTIONS)
def run_action(
    request: Request,
    req: ActionRequest,
    user: dict = Depends(get_current_user),
) -> ActionResponse:
    """
    Execute a named action on behalf of the authenticated user.

    `user_id` is always taken from the JWT — callers cannot spoof other users.
    `dry_run=true` logs intent but skips execution and audit.
    Unknown actions return 200 with ok=false (runtime validates).
    """
    result = agent_runtime.handle_action(
        user_id=user["email"],
        action=req.action,
        job_key=req.job_key,
        job=req.job,
        source=req.source,
        dry_run=req.dry_run,
    )
    return ActionResponse(**result.to_dict())
