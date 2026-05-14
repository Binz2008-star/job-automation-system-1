"""
src/schemas/agent.py
HTTP contracts for the Agent Interaction Layer.
All agent endpoints use these schemas for request parsing and response serialization.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── UI component types ────────────────────────────────────────────────────────

class AgentUIType(str, Enum):
    JOB_LIST        = "job_list"
    JOB_DETAIL      = "job_detail"
    APPLICATION_LIST = "application_list"
    STATS           = "stats"
    PIPELINE_STATUS = "pipeline_status"
    TEXT            = "text"
    CONFIRM         = "confirm"
    ERROR           = "error"


# ── Action styles ─────────────────────────────────────────────────────────────

class ActionStyle(str, Enum):
    PRIMARY   = "primary"
    SECONDARY = "secondary"
    DANGER    = "danger"


# ── Core types ────────────────────────────────────────────────────────────────

class AgentAction(BaseModel):
    """A single clickable action rendered alongside a UI component."""
    action_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:8],
        description="Short unique ID for deduplication",
    )
    type: str = Field(..., description="apply | skip | block | save | trigger_pipeline | view_detail")
    label: str
    style: ActionStyle = ActionStyle.SECONDARY
    job_id: Optional[str] = None
    job: Optional[Dict[str, Any]] = None  # full payload — enables stateless re-submission
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentUIComponent(BaseModel):
    """Renderer-ready UI payload; type tells the frontend which widget to mount."""
    type: AgentUIType
    title: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    """Internal result type returned by every tool function."""
    success: bool
    tool_name: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: int = 0


# ── HTTP request / response ───────────────────────────────────────────────────

class AgentChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language user message",
    )
    action: Optional[AgentAction] = Field(
        None,
        description="If set, bypasses intent detection and executes this action directly",
    )


class AgentUIResponse(BaseModel):
    """
    The single response envelope returned by POST /api/v1/agent/chat.
    Frontend renders `ui` based on ui.type; `actions` become clickable buttons.
    """
    message: str
    ui: Optional[AgentUIComponent] = None
    actions: List[AgentAction] = Field(default_factory=list)
    tool_used: Optional[str] = None
    execution_time_ms: int = 0
    success: bool = True
