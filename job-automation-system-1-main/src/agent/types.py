"""
src/agent/types.py
Shared types for the Rico agent runtime layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RuntimeResult:
    """
    The flat result type returned by AgentRuntime.handle_action().
    Designed to be easily serialised or forwarded to any UI layer
    (Telegram, REST, future web/mobile).
    """
    ok: bool
    message: str          # human-readable reply for the caller
    action: str           # the action that was (or would have been) executed
    job_key: str          # job fingerprint passed by the caller
    source: str           # "telegram" | "api" | "test" | …
    user_id: str
    dry_run: bool = False
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    confidence: float = 1.0  # 0.0–1.0; always 1.0 for explicit user actions
    explanation: str = ""    # why this action was chosen / what was done
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "action": self.action,
            "job_key": self.job_key,
            "source": self.source,
            "user_id": self.user_id,
            "dry_run": self.dry_run,
            "data": self.data,
            "error": self.error,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "duration_ms": self.duration_ms,
        }
