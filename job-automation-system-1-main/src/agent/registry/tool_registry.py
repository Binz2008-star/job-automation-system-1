"""
src/agent/registry/tool_registry.py
Central tool registry — maps tool names to their callables and metadata.

All tools are registered at module load time via _register().
The orchestrator and action executor both resolve tools through this module.
No tool implementation lives here; this is a lookup table only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    fn: Callable[..., Any]
    parameters: Dict[str, str] = field(default_factory=dict)


_REGISTRY: Dict[str, ToolDefinition] = {}


def _register(name: str, fn: Callable, description: str, parameters: Optional[Dict[str, str]] = None) -> None:
    _REGISTRY[name] = ToolDefinition(
        name=name,
        fn=fn,
        description=description,
        parameters=parameters or {},
    )


def get(name: str) -> ToolDefinition:
    """
    Retrieve a tool by name.
    Raises KeyError with a helpful message if the tool is not registered.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown tool {name!r}. Registered tools: {available}")
    return _REGISTRY[name]


def all_tools() -> Dict[str, ToolDefinition]:
    """Return a snapshot of the full registry (for inspection / tests)."""
    return dict(_REGISTRY)


def is_registered(name: str) -> bool:
    return name in _REGISTRY


# ── Tool registrations ────────────────────────────────────────────────────────
# Import here to trigger registration; kept at bottom to avoid circular deps.

from src.agent.tools.job_tools import (  # noqa: E402
    apply_job,
    block_company,
    get_ranked_jobs,
    save_job,
    search_jobs,
    skip_job,
)
from src.agent.tools.pipeline_tools import (  # noqa: E402
    get_pipeline_status,
    trigger_pipeline,
)
from src.agent.tools.stats_tools import get_application_stats  # noqa: E402
from src.agent.tools.messaging_tools import (  # noqa: E402
    draft_message,
    explain_match,
    set_reminder,
)

_register("search_jobs",           search_jobs,           "Search jobs by score/source/page")
_register("get_ranked_jobs",       get_ranked_jobs,       "Return top-scored jobs for the dashboard")
_register("apply_job",             apply_job,             "Trigger automated application for one job")
_register("skip_job",              skip_job,              "Mark a job as skipped")
_register("save_job",              save_job,              "Save a job for later review")
_register("block_company",         block_company,         "Block all future results from a company")
_register("get_pipeline_status",   get_pipeline_status,   "Return the latest pipeline run state")
_register("trigger_pipeline",      trigger_pipeline,      "Start the daily pipeline manually")
_register("get_application_stats", get_application_stats, "Return aggregate application statistics")
_register("draft_message",         draft_message,         "Generate a tailored application message for a job")
_register("explain_match",         explain_match,         "Explain why Rico recommended this job")
_register("set_reminder",          set_reminder,          "Set a 2-day reminder for a job")

logger.debug("tool_registry_loaded tools=%d names=%s", len(_REGISTRY), sorted(_REGISTRY))
