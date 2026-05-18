"""
Phase 1 IntentRouter wrapper around the existing legacy classifier.

Behavior:
  - Open-ended question gate runs first. Match -> ConversationalAIHandler.
  - Everything else returns a LEGACY-source decision and the existing
    classifier path stays unchanged.
"""
from __future__ import annotations

import logging

from .gates import is_open_ended_question
from .types import IntentDecision, IntentSource

logger = logging.getLogger(__name__)


class IntentRouter:
    """Stateless Phase 1 router."""

    VERSION: str = "phase1.1.0"
    _CONVERSATIONAL_CONFIDENCE: float = 0.95

    def route(
        self,
        *,
        message: str,
        user_id: str,
        profile_context_present: bool,
    ) -> IntentDecision:
        """Route a message to conversational AI or legacy classifier."""

        is_open, reason = is_open_ended_question(message)
        decision = (
            self._conversational(message, user_id, profile_context_present, reason)
            if is_open
            else self._legacy_passthrough(message, user_id, profile_context_present)
        )

        logger.info("intent_decision %s", decision.to_log_dict())
        return decision

    def _conversational(
        self,
        message: str,
        user_id: str,
        ctx_present: bool,
        reason: str,
    ) -> IntentDecision:
        return IntentDecision(
            intent="conversational",
            confidence=self._CONVERSATIONAL_CONFIDENCE,
            source=IntentSource.RULE,
            handler_name="ConversationalAIHandler",
            should_use_ai=True,
            raw_message=message,
            user_id=user_id,
            profile_context_present=ctx_present,
            reason=f"gate:{reason}",
        )

    def _legacy_passthrough(
        self,
        message: str,
        user_id: str,
        ctx_present: bool,
    ) -> IntentDecision:
        return IntentDecision(
            intent="legacy_passthrough",
            confidence=1.0,
            source=IntentSource.LEGACY,
            handler_name="LegacyClassifier",
            should_use_ai=False,
            raw_message=message,
            user_id=user_id,
            profile_context_present=ctx_present,
            reason="defer_to_legacy",
        )
