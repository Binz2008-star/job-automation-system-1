"""
Intent decision contract.

This dataclass is the single object produced by IntentRouter and consumed
by every handler. It survives unchanged through future phases; only the
classifier stages that produce it evolve.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentSource(str, Enum):
    """Which classifier stage produced the decision."""

    RULE = "rule"
    TAXONOMY = "taxonomy"
    LLM = "llm"
    FALLBACK = "fallback"
    LEGACY = "legacy"


@dataclass(frozen=True, slots=True)
class IntentDecision:
    """
    Normalized routing decision.

    Frozen + slotted keeps the object cheap and safe to pass around unchanged.
    """

    intent: str
    confidence: float
    source: IntentSource
    handler_name: str
    should_use_ai: bool
    raw_message: str
    user_id: str
    profile_context_present: bool
    entities: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_log_dict(self) -> dict[str, Any]:
        """Return a redacted, log-safe view of the routing decision."""
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "source": self.source.value,
            "handler_name": self.handler_name,
            "should_use_ai": self.should_use_ai,
            "user_id": self.user_id,
            "profile_context_present": self.profile_context_present,
            "message_hash": hashlib.sha256(
                self.raw_message.strip().lower().encode("utf-8")
            ).hexdigest()[:16],
            "message_len": len(self.raw_message),
            "reason": self.reason,
        }
