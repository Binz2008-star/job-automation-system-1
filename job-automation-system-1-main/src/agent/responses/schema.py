"""src/agent/responses/schema.py

Stable response contract for all Rico chat endpoints.

Every chat response — success or failure — MUST go through ``RicoResponse``
so the frontend can render by ``type`` instead of guessing from message text.

Fields:
    success      – whether the request completed without error
    type         – discriminator the frontend renders on
    message      – human-readable text
    matches      – job match list (only for type=job_matches)
    applications – tracked-application list (only for type=application_status)
    profile      – profile summary (only for type=profile_summary)
    options      – action buttons / choices (only for type=clarification|options)
    next_action  – suggested next step for the frontend
    debug_id     – opaque reference for server-side log correlation
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

ResponseType = Literal[
    "job_matches",
    "clarification",
    "application_status",
    "profile_summary",
    "profile_update",
    "onboarding",
    "cv_first_profile",
    "options",
    "confirmation_required",
    "preferences_updated",
    "interview_prep",
    "profile_skip",
    "profile_role_suggestions",
    "role_confirmation",
    "live_job_search_pending",
    "save_job",
    "draft_message",
    "explain_match",
    "error",
]


def _generate_debug_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class RicoResponse:
    """Canonical response envelope for every Rico chat interaction."""

    success: bool
    type: str
    message: str
    matches: List[Dict[str, Any]] = field(default_factory=list)
    applications: List[Dict[str, Any]] = field(default_factory=list)
    profile: Optional[Dict[str, Any]] = None
    options: List[Dict[str, Any]] = field(default_factory=list)
    next_action: Optional[str] = None
    debug_id: str = field(default_factory=_generate_debug_id)

    # ── passthrough metadata (added by _finalize, kept for backward compat) ──
    intent: Optional[str] = None
    entities: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    role_intelligence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict, omitting None/empty optional fields for clean JSON."""
        d: Dict[str, Any] = {
            "success": self.success,
            "type": self.type,
            "message": self.message,
            "debug_id": self.debug_id,
        }
        if self.matches:
            d["matches"] = self.matches
        if self.applications:
            d["applications"] = self.applications
        if self.profile is not None:
            d["profile"] = self.profile
        if self.options:
            d["options"] = self.options
        if self.next_action is not None:
            d["next_action"] = self.next_action
        if self.intent is not None:
            d["intent"] = self.intent
        if self.entities is not None:
            d["entities"] = self.entities
        if self.confidence is not None:
            d["confidence"] = self.confidence
        if self.role_intelligence is not None:
            d["role_intelligence"] = self.role_intelligence
        return d


def build_error_response(
    message: str = "Something went wrong.",
    *,
    debug_id: Optional[str] = None,
    log_exc: Optional[BaseException] = None,
    user_id: Optional[str] = None,
    intent: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a safe error response with ``debug_id`` for log correlation.

    Server-side logging includes full context; the client only sees the
    ``debug_id`` reference — never a raw stack trace.
    """
    did = debug_id or _generate_debug_id()
    if log_exc is not None:
        logger.error(
            "rico_error debug_id=%s user=%s intent=%s error=%s",
            did,
            user_id or "unknown",
            intent or "unknown",
            str(log_exc),
            exc_info=log_exc,
        )
    return RicoResponse(
        success=False,
        type="error",
        message=f"{message} Reference: {did}",
        debug_id=did,
    ).to_dict()
