"""
src/agent/runtime.py
Rico agent runtime — single entry point for all job actions.

Callers (Telegram, API, future UI layers) use one method:

    result = agent_runtime.handle_action(
        user_id  = user_id,
        action   = "apply",       # apply | save | skip | not_relevant |
                                  # draft | why | remind | block
        job_key  = job_key,       # hex fingerprint from get_job_id()
        job      = job_dict,      # full dict if available; else resolved from cache
        source   = "telegram",    # "telegram" | "api" | "test" | …
        dry_run  = False,         # True = log intent, skip side effects
    )

All state-changing actions are:
  - idempotency-guarded (no double-applies)
  - audit-logged
  - routed through the registered tool in the tool registry

Interactive code is unreachable from this module.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Optional

from src.agent.orchestrator.intent_detector import ACTION_TO_TOOL, VALID_ACTION_TYPES
from src.agent.registry import tool_registry
from src.agent.types import RuntimeResult
from src.repositories.audit_repo import IDEMPOTENT_ACTION_TYPES, is_duplicate, log_action

logger = logging.getLogger(__name__)

# Actions with side effects that must pass the idempotency guard
_IDEMPOTENT = frozenset(IDEMPOTENT_ACTION_TYPES)

# Confidence level by action category (explicit user choice → 1.0)
_CONFIDENCE: Dict[str, float] = {
    "apply": 1.0, "save": 1.0, "skip": 1.0, "not_relevant": 1.0,
    "block": 1.0, "draft": 1.0, "why": 1.0, "remind": 1.0,
    "trigger_pipeline": 1.0,
}

_REPLY: Dict[str, str] = {
    "apply":        "Marked as applied. Rico will track this job.",
    "save":         "Saved. Rico will keep this job in your tracker.",
    "skip":         "Skipped. Rico noted your feedback.",
    "not_relevant": "Marked not relevant. Rico will reduce similar matches.",
    "block":        "Company blocked. Rico will exclude it from future results.",
    "draft":        "",   # filled from tool data
    "why":          "",   # filled from tool data
    "remind":       "",   # filled from tool data
}


class AgentRuntime:
    """
    Central dispatcher for Rico agent actions.
    Stateless and thread-safe — a single module-level instance is exported.
    """

    def handle_action(
        self,
        user_id: str,
        action: str,
        job_key: str = "",
        job: Optional[Dict[str, Any]] = None,
        source: str = "api",
        dry_run: bool = False,
    ) -> RuntimeResult:
        """
        Execute a single named action on behalf of a user.

        Args:
            user_id:  Identifies the user (Telegram chat_id, email, etc.)
            action:   One of VALID_ACTION_TYPES
            job_key:  Fingerprint from get_job_id() — used to look up job if
                      `job` dict not provided
            job:      Full job dict. If None, resolved from Telegram job cache.
            source:   Caller label for audit logs ("telegram", "api", …)
            dry_run:  When True, the action is NOT executed; only logged.

        Returns:
            RuntimeResult — always returned, never raises.
        """
        wall_start = time.monotonic()

        # Stable idempotency key: same user + action + job within the TTL window
        # is treated as a duplicate regardless of which surface triggered it.
        _idem_raw = f"{user_id}:{action}:{job_key}"
        action_id = hashlib.md5(_idem_raw.encode(), usedforsecurity=False).hexdigest()[:16]

        # 1. Validate action
        if action not in VALID_ACTION_TYPES:
            return RuntimeResult(
                ok=False,
                message=f"Unknown action '{action}'. Supported: {sorted(VALID_ACTION_TYPES)}",
                action=action, job_key=job_key, source=source, user_id=user_id,
                error=f"unknown_action:{action}",
                duration_ms=int((time.monotonic() - wall_start) * 1000),
            )

        # 2. Resolve job dict
        resolved_job = self._resolve_job(job, job_key)

        # 3. Idempotency guard for state-changing actions
        if action in _IDEMPOTENT and is_duplicate(action_id):
            logger.info("runtime_duplicate_skipped action=%s user=%s", action, user_id)
            return RuntimeResult(
                ok=False,
                message="This action was already executed for this job.",
                action=action, job_key=job_key, source=source, user_id=user_id,
                error="duplicate_action",
                duration_ms=int((time.monotonic() - wall_start) * 1000),
            )

        # 4. Dry-run: return what would happen without executing
        if dry_run:
            tool_name = ACTION_TO_TOOL[action]
            msg = f"[DRY RUN] Would execute '{tool_name}' for '{resolved_job.get('title','unknown')}'"
            logger.info("runtime_dry_run action=%s tool=%s user=%s source=%s", action, tool_name, user_id, source)
            return RuntimeResult(
                ok=True,
                message=msg,
                action=action, job_key=job_key, source=source, user_id=user_id,
                dry_run=True,
                confidence=_CONFIDENCE.get(action, 1.0),
                explanation=f"dry_run: {tool_name} on {resolved_job.get('title','?')}",
                duration_ms=int((time.monotonic() - wall_start) * 1000),
            )

        # 5. Execute tool
        tool_name = ACTION_TO_TOOL[action]
        try:
            tool_def = tool_registry.get(tool_name)
        except KeyError as exc:
            return RuntimeResult(
                ok=False, message="Tool not available.",
                action=action, job_key=job_key, source=source, user_id=user_id,
                error=str(exc),
                duration_ms=int((time.monotonic() - wall_start) * 1000),
            )

        logger.info(
            "runtime_execute action=%s tool=%s user=%s source=%s job=%r",
            action, tool_name, user_id, source, resolved_job.get("title", ""),
        )

        try:
            tool_result = tool_def.fn(resolved_job)
        except Exception as exc:
            logger.exception("runtime_tool_error action=%s tool=%s", action, tool_name)
            tool_result = None
            error_str = str(exc)
        else:
            error_str = tool_result.error if tool_result and not tool_result.success else None

        elapsed = int((time.monotonic() - wall_start) * 1000)
        tool_ok = bool(tool_result and tool_result.success)
        tool_data = (tool_result.data or {}) if tool_result else {}

        # 6. Build message
        message = self._build_message(action, tool_ok, tool_data, error_str)

        # 7. Audit log
        self._audit(
            action_id=action_id, action=action, user_id=user_id,
            job=resolved_job, source=source, ok=tool_ok,
            message=message, error=error_str, duration_ms=elapsed,
        )

        return RuntimeResult(
            ok=tool_ok,
            message=message,
            action=action,
            job_key=job_key,
            source=source,
            user_id=user_id,
            dry_run=False,
            data=tool_data,
            error=error_str,
            confidence=_CONFIDENCE.get(action, 1.0),
            explanation=f"{tool_name} executed via {source}",
            duration_ms=elapsed,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_job(job: Optional[Dict[str, Any]], job_key: str) -> Dict[str, Any]:
        """Return the best available job dict. Falls back to a stub with the key."""
        if job:
            return job
        if job_key:
            try:
                from src.rico_telegram_ui import lookup_job
                cached = lookup_job(job_key)
                if cached:
                    return cached
            except Exception:
                pass
        return {"id": job_key} if job_key else {}

    @staticmethod
    def _build_message(
        action: str, ok: bool, data: Dict[str, Any], error: Optional[str]
    ) -> str:
        if not ok:
            return f"Action failed: {error or 'unknown error'}"

        # Actions whose reply comes from tool output
        if action == "draft":
            return data.get("draft") or "Draft message could not be generated."
        if action == "why":
            return data.get("explanation") or "No explanation available."
        if action == "remind":
            reminder_date = data.get("reminder_date", "")
            return f"Reminder set for {reminder_date}." if reminder_date else "Reminder noted."

        return _REPLY.get(action, "Action completed.")

    @staticmethod
    def _audit(
        action_id: str, action: str, user_id: str,
        job: Dict[str, Any], source: str,
        ok: bool, message: str, error: Optional[str], duration_ms: int,
    ) -> None:
        try:
            from datetime import datetime, timezone
            log_action({
                "action_id":      action_id,
                "action_type":    action,
                "user_email":     user_id,
                "job_id":         str(job.get("id") or job.get("_key") or ""),
                "job_title":      job.get("title"),
                "job_company":    job.get("company"),
                "timestamp":      datetime.now(timezone.utc).isoformat(),
                "result_status":  "success" if ok else "failure",
                "result_message": message,
                "duration_ms":    duration_ms,
                "failure_reason": error if not ok else None,
                "source":         source,
            })
        except Exception:
            logger.exception("runtime_audit_failed action=%s", action)


# Module-level singleton — import and use directly:
#   from src.agent.runtime import agent_runtime
agent_runtime = AgentRuntime()
