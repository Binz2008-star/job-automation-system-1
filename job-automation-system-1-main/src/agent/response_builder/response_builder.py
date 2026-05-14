"""
src/agent/response_builder/response_builder.py
Converts a ToolExecutionResult into a renderer-ready AgentUIResponse.

This is the only module that instantiates AgentUIResponse.
No business logic lives here — only presentation decisions:
  • which UI type to render
  • which actions to attach
  • what human-readable message to compose
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from src.schemas.agent import (
    ActionStyle,
    AgentAction,
    AgentUIComponent,
    AgentUIResponse,
    AgentUIType,
    ToolExecutionResult,
)

logger = logging.getLogger(__name__)

# ── Public entry point ────────────────────────────────────────────────────────

def build_response(
    result: ToolExecutionResult,
    original_message: str = "",
    original_action: Optional[AgentAction] = None,
) -> AgentUIResponse:
    """Dispatch to the appropriate builder based on tool name and success."""
    if not result.success:
        return _error_response(result)

    tool = result.tool_name
    data = result.data or {}

    # Use match statement for cleaner dispatch (Python 3.10+)
    match tool:
        case "get_ranked_jobs" | "search_jobs":
            response = _job_list_response(result, data)
        case "apply_job":
            response = _apply_response(result, data, original_action)
        case "skip_job":
            response = _skip_response(result, data, original_action)
        case "save_job":
            response = _save_response(result, original_action)
        case "block_company":
            response = _block_response(result, data, original_action)
        case "get_application_stats":
            response = _stats_response(result, data)
        case "get_pipeline_status":
            response = _pipeline_status_response(result, data)
        case "trigger_pipeline":
            response = _pipeline_trigger_response(result, data)
        case "get_market_trends":
            response = _market_insights_response(result, data)
        case "get_application_strategy":
            response = _strategy_response(result, data)
        case "get_learning_profile":
            response = _learning_profile_response(result, data)
        case "help":
            response = _help_response()
        case _:
            # Unknown tool — return raw data as text fallback
            response = AgentUIResponse(
                message=f"Result from {tool}.",
                ui=AgentUIComponent(type=AgentUIType.TEXT, data=data),
                tool_used=tool,
                success=True,
            )

    logger.debug(
        "build_response",
        extra={
            "tool": result.tool_name,
            "success": result.success,
            "ui_type": response.ui.type.value if response.ui else "unknown",
        },
    )
    return response


# ── Individual builders ───────────────────────────────────────────────────────

def _job_list_response(result: ToolExecutionResult, data: Dict[str, Any]) -> AgentUIResponse:
    jobs = data.get("jobs", [])
    total = data.get("total", 0)
    page = data.get("page", 1)
    page_size = data.get("page_size", 20)
    has_more = data.get("has_more", False)

    if not jobs:
        return AgentUIResponse(
            message="No jobs match your current filters. Try lowering the minimum score in Settings.",
            ui=AgentUIComponent(type=AgentUIType.TEXT, data={"hint": "no_results"}),
            tool_used=result.tool_name,
            success=True,
        )

    count = len(jobs)
    message = (
        f"Here are your top {count} job match{'es' if count != 1 else ''} "
        f"(page {page} of {((total + page_size - 1) // page_size)}). "
        "Click Apply, Skip, or Save on each card."
    )

    actions = _job_actions_for_list(jobs)

    # Add pagination action if more results available
    if has_more:
        actions.append(
            AgentAction(
                type="load_more",
                label="Load more jobs",
                style=ActionStyle.SECONDARY,
                metadata={"page": page + 1, "page_size": page_size},
            )
        )

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(
            type=AgentUIType.JOB_LIST,
            title=f"Top {count} Matches",
            data={"jobs": jobs, "total": total, "page": page, "has_more": has_more},
        ),
        actions=actions,
        tool_used=result.tool_name,
        success=True,
    )


def _job_actions_for_list(jobs: List[Dict[str, Any]]) -> List[AgentAction]:
    """One Apply + Skip + Save action per job, labelled with the job title."""
    actions: List[AgentAction] = []
    for job in jobs:
        job_id = str(job.get("id", job.get("link", "")))
        title_short = (job.get("title") or "Job")[:40]

        actions.append(AgentAction(
            action_id=_deterministic_action_id("apply", job),
            type="apply",
            label=f"Apply — {title_short}",
            style=ActionStyle.PRIMARY,
            job_id=job_id,
            job=job,
        ))
        actions.append(AgentAction(
            action_id=_deterministic_action_id("skip", job),
            type="skip",
            label="Skip",
            style=ActionStyle.SECONDARY,
            job_id=job_id,
            job=job,
        ))
        actions.append(AgentAction(
            action_id=_deterministic_action_id("save", job),
            type="save",
            label="Save",
            style=ActionStyle.SECONDARY,
            job_id=job_id,
            job=job,
        ))
    return actions


def _apply_response(
    result: ToolExecutionResult,
    data: Dict[str, Any],
    action: Optional[AgentAction],
) -> AgentUIResponse:
    title = _job_title(action)
    status = data.get("status", "unknown")
    msg = data.get("message", "")

    if status in ("applied", "success"):
        message = f"Successfully applied to **{title}**. {msg}"
    elif status == "dry_run":
        message = f"Dry run complete for **{title}** — no form was submitted. {msg}"
    elif status == "already_applied":
        message = f"You have already applied to **{title}**."
    elif status == "unsupported":
        message = f"No automation engine supports this source. {msg}"
    else:
        message = f"Application attempt for **{title}**: {msg or status}"

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(
            type=AgentUIType.CONFIRM,
            title="Application Result",
            data={"status": status, "title": title, **data},
        ),
        tool_used=result.tool_name,
        success=True,
    )


def _skip_response(
    result: ToolExecutionResult,
    data: Dict[str, Any],
    action: Optional[AgentAction],
) -> AgentUIResponse:
    title = _job_title(action)
    skipped = data.get("skipped", True)
    if skipped:
        message = f"Skipped **{title}**. It won't appear in future results."
    else:
        message = f"**{title}** was already tracked — no change made."

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(type=AgentUIType.CONFIRM, data={"skipped": skipped, "title": title}),
        tool_used=result.tool_name,
        success=True,
    )


def _save_response(
    result: ToolExecutionResult,
    action: Optional[AgentAction],
) -> AgentUIResponse:
    title = _job_title(action)
    return AgentUIResponse(
        message=f"Saved **{title}** for later review.",
        ui=AgentUIComponent(type=AgentUIType.CONFIRM, data={"title": title}),
        tool_used=result.tool_name,
        success=True,
    )


def _block_response(
    result: ToolExecutionResult,
    data: Dict[str, Any],
    action: Optional[AgentAction],
) -> AgentUIResponse:
    # Fix: data is always a dict, extract company from it or fallback to action
    company = data.get("company") or _job_company(action)
    return AgentUIResponse(
        message=(
            f"Blocked **{company}**. Future results from this company will be suppressed. "
            "Add to EXCLUDE_KEYWORDS in .env to persist across restarts."
        ),
        ui=AgentUIComponent(type=AgentUIType.CONFIRM, data={"blocked_company": company}),
        tool_used=result.tool_name,
        success=True,
    )


def _stats_response(result: ToolExecutionResult, data: Dict[str, Any]) -> AgentUIResponse:
    total = data.get("total_applied", 0)
    interviews = data.get("interviews_scheduled", 0)
    rate = data.get("success_rate", 0.0)

    message = (
        f"You've applied to **{total}** jobs. "
        f"**{interviews}** interview{'s' if interviews != 1 else ''} scheduled "
        f"({rate}% success rate)."
    )

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(type=AgentUIType.STATS, title="Application Progress", data=data),
        actions=[
            AgentAction(
                type="trigger_pipeline",
                label="Run Pipeline Now",
                style=ActionStyle.SECONDARY,
            )
        ],
        tool_used=result.tool_name,
        success=True,
    )


def _pipeline_status_response(result: ToolExecutionResult, data: Dict[str, Any]) -> AgentUIResponse:
    status = data.get("status", "idle")
    started = data.get("started_at", "—")
    finished = data.get("finished_at")

    if status == "running":
        message = f"Pipeline is currently **running** (started: {started})."
    elif status == "done":
        message = f"Last pipeline run **completed** at {finished or started}."
    elif status == "failed":
        err = data.get("error", "unknown error")
        message = f"Last pipeline run **failed**: {err}"
    else:
        message = "No pipeline runs recorded yet."

    actions = []
    if status != "running":
        actions.append(AgentAction(
            type="trigger_pipeline",
            label="Run Pipeline Now",
            style=ActionStyle.PRIMARY,
        ))

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(type=AgentUIType.PIPELINE_STATUS, data=data),
        actions=actions,
        tool_used=result.tool_name,
        success=True,
    )


def _pipeline_trigger_response(result: ToolExecutionResult, data: Dict[str, Any]) -> AgentUIResponse:
    return AgentUIResponse(
        message="Pipeline started. It runs in the background — check status in a minute.",
        ui=AgentUIComponent(
            type=AgentUIType.PIPELINE_STATUS,
            data={"status": "running", **data},
        ),
        tool_used=result.tool_name,
        success=True,
    )


def _error_response(result: ToolExecutionResult) -> AgentUIResponse:
    error_msg = result.error or "unknown error"
    return AgentUIResponse(
        message=f"❌ {error_msg}. Try again or use a different request.",
        ui=AgentUIComponent(
            type=AgentUIType.ERROR,
            data={"error": result.error, "tool": result.tool_name},
        ),
        actions=[
            AgentAction(
                type="help",
                label="Get Help",
                style=ActionStyle.SECONDARY,
            )
        ],
        tool_used=result.tool_name,
        success=False,
    )


def _help_response() -> AgentUIResponse:
    return AgentUIResponse(
        message=(
            "Here's what you can ask me:\n"
            "• **Show me today's best jobs** — ranked job matches\n"
            "• **Application stats** — progress report\n"
            "• **Pipeline status** — last run info\n"
            "• **Trigger pipeline** — run the job search now\n"
            "• **Market insights** — UAE market health and trends\n"
            "• **Application strategy** — personalized application approach\n"
            "• **Learning profile** — your preferences and inferred roles\n"
            "\nOr click Apply / Skip / Save on any job card."
        ),
        ui=AgentUIComponent(
            type=AgentUIType.TEXT,
            title="Available Commands",
            data={
                "commands": [
                    "Show me today's best jobs",
                    "Application stats",
                    "Pipeline status",
                    "Trigger pipeline",
                    "Market insights",
                    "Application strategy",
                    "Learning profile",
                ]
            },
        ),
        tool_used="help",
        success=True,
    )


def _market_insights_response(result: ToolExecutionResult, data: Dict[str, Any]) -> AgentUIResponse:
    """Builder for market insights (UAE-specific)."""
    health = data.get("market_health", {})
    status = health.get("status", "Unknown")
    health_score = health.get("health_score", 0)
    recommendations = data.get("recommendations", [])

    message = (
        f"Market health: **{status}** (score: {health_score}/100). "
        f"{recommendations[0] if recommendations else 'No specific recommendations.'}"
    )

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(type=AgentUIType.TEXT, data=data),
        actions=[
            AgentAction(
                type="show_strategy",
                label="View Strategy",
                style=ActionStyle.SECONDARY,
            )
        ],
        tool_used=result.tool_name,
        success=True,
    )


def _strategy_response(result: ToolExecutionResult, data: Dict[str, Any]) -> AgentUIResponse:
    """Builder for application strategy."""
    strategy = data.get("strategy", {})
    approach = strategy.get("approach", "Standard")
    tips = data.get("tips", [])

    message = f"Your recommended application approach: **{approach}**."
    if tips:
        message += f" Key tips: {', '.join(tips[:3])}"

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(type=AgentUIType.TEXT, data=data),
        actions=[
            AgentAction(
                type="show_market_insights",
                label="View Market Insights",
                style=ActionStyle.SECONDARY,
            )
        ],
        tool_used=result.tool_name,
        success=True,
    )


def _learning_profile_response(result: ToolExecutionResult, data: Dict[str, Any]) -> AgentUIResponse:
    """Builder for learning profile (user preferences)."""
    role_preferences = data.get("role_preferences", {})
    top_roles = list(role_preferences.items())[:3] if role_preferences else []
    skill_confidence = data.get("skill_confidence", {})

    message = f"You've shown interest in **{len(role_preferences)}** roles."
    if top_roles:
        roles_str = ", ".join([f"{role} ({score:.1f})" for role, score in top_roles])
        message += f" Top interests: {roles_str}"

    if skill_confidence:
        top_skills = sorted(skill_confidence.items(), key=lambda x: x[1], reverse=True)[:3]
        skills_str = ", ".join([skill for skill, _ in top_skills])
        message += f". Strong skills: {skills_str}"

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(type=AgentUIType.TEXT, data=data),
        actions=[
            AgentAction(
                type="update_preferences",
                label="Update Preferences",
                style=ActionStyle.SECONDARY,
            )
        ],
        tool_used=result.tool_name,
        success=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_title(action: Optional[AgentAction]) -> str:
    if action and action.job:
        return action.job.get("title") or "Unknown job"
    return "Unknown job"


def _job_company(action: Optional[AgentAction]) -> str:
    if action and action.job:
        return action.job.get("company") or "Unknown company"
    return "Unknown company"


def _deterministic_action_id(action_type: str, job: Dict[str, Any]) -> str:
    """
    SHA-256[:12] of "type:link".
    The same action on the same job always produces the same action_id,
    enabling idempotency checks in the audit repository.

    Fallback to composite key if link is missing to prevent collisions.
    """
    link = (job.get("link") or "").strip()
    # Use composite key if link is empty to prevent collisions
    if not link:
        link = f"{job.get('id', '')}:{job.get('title', '')}:{job.get('company', '')}"
    key = f"{action_type}:{link}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]
