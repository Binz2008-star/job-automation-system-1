"""Persistent memory store for Rico AI.

This file gives Rico a lightweight multi-user memory layer before a full
PostgreSQL profile service is added. It stores user profiles, preferences,
chat history, agent permissions, learning signals, and semantic memories in
JSON files so Rico can behave like a real agent immediately.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from src.rico_agent import RicoAgentSettings, RicoProfile

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RICO_MEMORY_DIR = DATA_DIR / "rico"
RICO_MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _safe_key(user_id: str) -> str:
    """Return a sha256 hex digest of user_id safe for use as a filename component."""
    return hashlib.sha256(user_id.encode()).hexdigest()


def _assert_contained(path: Path) -> Path:
    """Raise ValueError if path resolves outside RICO_MEMORY_DIR."""
    try:
        path.resolve().relative_to(RICO_MEMORY_DIR.resolve())
    except ValueError:
        raise ValueError(f"Path traversal blocked: {path}")
    return path

MEMORY_TYPES = {
    "preference",
    "behavior",
    "outcome",
    "conversation",
    "reminder",
    "system",
}


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_+-]+", text.lower()) if len(t) > 2}


def _similarity(query: str, content: str) -> float:
    q = _tokenize(query)
    c = _tokenize(content)
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    return overlap / math.sqrt(len(q) * len(c))


class RicoMemoryStore:
    """JSON-backed Rico memory store."""

    def _profile_path(self, user_id: str) -> Path:
        return _assert_contained(RICO_MEMORY_DIR / f"profile_{_safe_key(user_id)}.json")

    def _chat_path(self, user_id: str) -> Path:
        return _assert_contained(RICO_MEMORY_DIR / f"chat_{_safe_key(user_id)}.json")

    def _signals_path(self, user_id: str) -> Path:
        return _assert_contained(RICO_MEMORY_DIR / f"signals_{_safe_key(user_id)}.json")

    def _memories_path(self, user_id: str) -> Path:
        return _assert_contained(RICO_MEMORY_DIR / f"memories_{_safe_key(user_id)}.json")

    def _conversation_state_path(self, user_id: str) -> Path:
        return _assert_contained(RICO_MEMORY_DIR / f"conversation_state_{_safe_key(user_id)}.json")

    def save_profile(self, profile: RicoProfile) -> None:
        payload = asdict(profile)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._profile_path(profile.user_id).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_profile(self, user_id: str) -> Optional[RicoProfile]:
        path = self._profile_path(user_id)
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        settings_data = data.pop("settings", {}) or {}
        data.pop("updated_at", None)
        settings = RicoAgentSettings(**settings_data)
        return RicoProfile(**data, settings=settings)

    def upsert_profile_from_dict(self, user_id: str, updates: Dict[str, Any]) -> RicoProfile:
        profile = self.load_profile(user_id)
        if profile is None:
            profile = RicoProfile(user_id=user_id)

        settings_updates = updates.pop("settings", None)
        for key, value in updates.items():
            if hasattr(profile, key) and value is not None:
                setattr(profile, key, value)

        if settings_updates:
            for key, value in settings_updates.items():
                if hasattr(profile.settings, key) and value is not None:
                    setattr(profile.settings, key, value)

        self.save_profile(profile)
        return profile

    def append_chat_message(self, user_id: str, role: str, message: str) -> None:
        history = self.load_chat_history(user_id)
        history.append({
            "role": role,
            "message": message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        self._chat_path(user_id).write_text(
            json.dumps(history[-200:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if role == "user" and message:
            self.add_memory(
                user_id=user_id,
                memory_type="conversation",
                content=message,
                source="chat",
                confidence=0.55,
            )

    def load_chat_history(self, user_id: str) -> List[Dict[str, Any]]:
        path = self._chat_path(user_id)
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else []
        except (json.JSONDecodeError, OSError):
            logger.warning("rico_memory: corrupt/empty chat history for user=%s — resetting", user_id)
            return []

    def record_learning_signal(self, user_id: str, job_id: str, action: str) -> None:
        signals = self.load_learning_signals(user_id)
        signals.append({
            "job_id": job_id,
            "action": action,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        self._signals_path(user_id).write_text(
            json.dumps(signals[-500:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.add_memory(
            user_id=user_id,
            memory_type="behavior",
            content=f"User action on job {job_id}: {action}",
            source="learning_signal",
            confidence=0.75,
            metadata={"job_id": job_id, "action": action},
        )

    def load_learning_signals(self, user_id: str) -> List[Dict[str, Any]]:
        path = self._signals_path(user_id)
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else []
        except (json.JSONDecodeError, OSError):
            logger.warning("rico_memory: corrupt/empty signals for user=%s — resetting", user_id)
            return []

    def load_memories(self, user_id: str) -> List[Dict[str, Any]]:
        path = self._memories_path(user_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def save_memories(self, user_id: str, memories: List[Dict[str, Any]]) -> None:
        self._memories_path(user_id).write_text(
            json.dumps(memories[-1000:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_memory(
        self,
        user_id: str,
        memory_type: str,
        content: str,
        source: str = "manual",
        confidence: float = 0.7,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        memory_type = memory_type if memory_type in MEMORY_TYPES else "system"
        memories = self.load_memories(user_id)
        now = datetime.now(timezone.utc).isoformat()
        memory_id = f"mem_{len(memories) + 1}_{int(datetime.now(timezone.utc).timestamp())}"
        entry = {
            "id": memory_id,
            "memory_type": memory_type,
            "content": content.strip(),
            "source": source,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        memories.append(entry)
        self.save_memories(user_id, memories)
        return entry

    def search_memories(
        self,
        user_id: str,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        memories = self.load_memories(user_id)
        scored: List[Dict[str, Any]] = []
        for memory in memories:
            if memory_type and memory.get("memory_type") != memory_type:
                continue
            score = _similarity(query, memory.get("content", ""))
            if score <= 0 and query:
                continue
            item = dict(memory)
            item["relevance"] = round(score, 4)
            scored.append(item)
        scored.sort(key=lambda m: (m.get("relevance", 0), m.get("confidence", 0)), reverse=True)
        return scored[:limit]

    def summarize_recent_memory(self, user_id: str, limit: int = 10) -> str:
        memories = self.load_memories(user_id)[-limit:]
        if not memories:
            return "No stored memory yet."
        lines = []
        for memory in memories:
            lines.append(f"- {memory.get('memory_type')}: {memory.get('content')}")
        return "\n".join(lines)

    def list_profiles(self) -> List[str]:
        # Returns sha256-keyed stems; callers that need readable IDs must map externally.
        return [p.stem.replace("profile_", "") for p in RICO_MEMORY_DIR.glob("profile_*.json")]

    def save_conversation_state(self, user_id: str, state: Dict[str, Any]) -> None:
        """Save conversation state (pending confirmations, active search context)."""
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._conversation_state_path(user_id).write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_conversation_state(self, user_id: str) -> Dict[str, Any]:
        """Load conversation state for a user."""
        path = self._conversation_state_path(user_id)
        if not path.exists():
            return {}
        try:
            content = path.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else {}
        except (json.JSONDecodeError, OSError):
            logger.warning("rico_memory: corrupt/empty conversation state for user=%s — resetting", user_id)
            return {}

    def clear_conversation_state(self, user_id: str) -> None:
        """Clear conversation state for a user."""
        path = self._conversation_state_path(user_id)
        if path.exists():
            path.unlink()

    def set_pending_confirmation(
        self,
        user_id: str,
        action: str,
        role: str,
        reason: str,
    ) -> None:
        """Set a pending confirmation state."""
        state = self.load_conversation_state(user_id)
        state["pending_confirmation"] = {
            "pending_action": action,
            "pending_role": role,
            "pending_reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_conversation_state(user_id, state)

    def get_pending_confirmation(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get and clear pending confirmation state."""
        state = self.load_conversation_state(user_id)
        pending = state.pop("pending_confirmation", None)
        if pending:
            self.save_conversation_state(user_id, state)
        return pending

    def set_active_search_context(
        self,
        user_id: str,
        role: str,
        result_count: int,
        fallback_roles: List[str],
        next_action: str,
    ) -> None:
        """Set active search context state."""
        state = self.load_conversation_state(user_id)
        state["active_search"] = {
            "active_role": role,
            "last_result_count": result_count,
            "fallback_roles": fallback_roles,
            "next_action": next_action,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_conversation_state(user_id, state)

    def get_active_search_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get active search context state."""
        state = self.load_conversation_state(user_id)
        return state.get("active_search")

    def clear_active_search_context(self, user_id: str) -> None:
        """Clear active search context state."""
        state = self.load_conversation_state(user_id)
        state.pop("active_search", None)
        self.save_conversation_state(user_id, state)
