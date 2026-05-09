"""
src/agent/orchestrator/intent_detector.py
Deterministic keyword-based intent detection.
No LLM calls, no embeddings — pure string matching ordered by specificity.

Each intent maps to a single canonical tool name in the registry.
Add entries to INTENT_PATTERNS to extend without touching the orchestrator.
"""
from __future__ import annotations

from typing import Optional, Tuple

# Intent → (tool_name, list_of_trigger_keywords)
# First match wins — order by specificity (most specific first).
_INTENT_TABLE: list[Tuple[str, str, list[str]]] = [
    (
        "trigger_pipeline",
        "trigger_pipeline",
        ["trigger", "run pipeline", "start pipeline", "kick off", "run now"],
    ),
    (
        "get_pipeline_status",
        "get_pipeline_status",
        ["pipeline", "last run", "pipeline status", "schedule", "when did"],
    ),
    (
        "get_application_stats",
        "get_application_stats",
        [
            "stats", "statistics", "how many", "applications", "progress",
            "report", "summary", "success rate", "interview", "rejection",
        ],
    ),
    (
        "get_ranked_jobs",
        "get_ranked_jobs",
        [
            "best jobs", "top jobs", "ranked", "today", "new jobs",
            "show jobs", "show me", "list jobs", "any jobs", "what jobs",
            "jobs today", "find jobs", "search", "match",
        ],
    ),
]

_FALLBACK_INTENT = "help"
_FALLBACK_TOOL: Optional[str] = None   # help has no tool


def detect(message: str) -> Tuple[str, Optional[str]]:
    """
    Return (intent_name, tool_name_or_None) for the given message.
    Falls back to ("help", None) when nothing matches.
    """
    lower = message.lower().strip()
    for intent, tool, keywords in _INTENT_TABLE:
        if any(kw in lower for kw in keywords):
            return intent, tool
    return _FALLBACK_INTENT, _FALLBACK_TOOL


# ── Supported actions (for action-execution path) ─────────────────────────────

# Maps action.type → tool_name
ACTION_TO_TOOL: dict[str, str] = {
    "apply":            "apply_job",
    "skip":             "skip_job",
    "save":             "save_job",
    "block":            "block_company",
    "trigger_pipeline": "trigger_pipeline",
}

VALID_ACTION_TYPES = frozenset(ACTION_TO_TOOL)
