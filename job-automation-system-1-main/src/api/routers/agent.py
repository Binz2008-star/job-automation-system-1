"""
src/api/routers/agent.py
POST /api/v1/agent/chat — agent interaction endpoint.
Passes user identity to the orchestrator for audit logging.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.agent.orchestrator.orchestrator import process
from src.api.deps import get_current_user
from src.schemas.agent import AgentChatRequest, AgentUIResponse

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/chat", response_model=AgentUIResponse)
def agent_chat(
    req: AgentChatRequest,
    user: dict = Depends(get_current_user),
) -> AgentUIResponse:
    """
    Process a natural-language message or execute a direct action.
    All actions are audit-logged and idempotency-checked before execution.
    """
    return process(req.message, req.action, user_email=user.get("email", "anonymous"))
