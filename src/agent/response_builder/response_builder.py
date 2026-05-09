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
from typing import Any, Dict, List, Optional

from src.schemas.agent import (
    ActionStyle,
    AgentAction,
    AgentUIComponent,
    AgentUIResponse,
    AgentUIType,
    ToolExecutionResult,
)

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

    if tool in ("get_ranked_jobs", "search_jobs"):
        return _job_list_response(result, data)

    if tool in ("apply_job",):
        return _apply_response(result, data, original_action)

    if tool in ("skip_job",):
        return _skip_response(result, data, original_action)

    if tool in ("save_job",):
        return _save_response(result, original_action)

    if tool in ("block_company",):
        return _block_response(result, data, original_action)

    if tool == "get_application_stats":
        return _stats_response(result, data)

    if tool in ("get_pipeline_status",):
        return _pipeline_status_response(result, data)

    if tool == "trigger_pipeline":
        return _pipeline_trigger_response(result, data)

    if tool == "help":
        return _help_response()

    # Unknown tool — return raw data as text fallback
    return AgentUIResponse(
        message=f"Result from {tool}.",
        ui=AgentUIComponent(type=AgentUIType.TEXT, data=data),
        tool_used=tool,
        success=True,
    )


# ── Individual builders ───────────────────────────────────────────────────────

def _job_list_response(result: ToolExecutionResult, data: Dict[str, Any]) -> AgentUIResponse:
    jobs = data.get("jobs", [])
    total = data.get("total", 0)

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
        f"(out of {total} total). "
        "Click Apply, Skip, or Save on each card."
    )

    actions = _job_actions_for_list(jobs)

    return AgentUIResponse(
        message=message,
        ui=AgentUIComponent(
            type=AgentUIType.JOB_LIST,
            title=f"Top {count} Matches",
            data={"jobs": jobs, "total": total},
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
    company = data if isinstance(data, str) else _job_company(action)
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
    return AgentUIResponse(
        message=f"Something went wrong: {result.error or 'unknown error'}",
        ui=AgentUIComponent(
            type=AgentUIType.ERROR,
            data={"error": result.error, "tool": result.tool_name},
        ),
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
                ]
            },
        ),
        tool_used="help",
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
    """
    link = (job.get("link") or "").strip()
    key = f"{action_type}:{link}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]
