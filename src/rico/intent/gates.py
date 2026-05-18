"""
Phase 1 open-ended question gate.

Pure lexical and punctuation signals. No taxonomy lookup, no model call.
Anything not matched here passes through to the legacy classifier unchanged.
"""
from __future__ import annotations

import re
from typing import Final

_OPENING_TOKENS: Final[frozenset[str]] = frozenset({
    "how", "what", "whats", "what's",
    "why", "when", "where", "who", "whom", "whose", "which",
    "can", "could", "should", "would",
    "explain",
})

_OPENING_PHRASES: Final[tuple[str, ...]] = (
    "do you",
    "did you",
    "are you",
    "is it",
    "tell me",
    "show me",
    "let me know",
)

_QUESTION_CHARS: Final[frozenset[str]] = frozenset("?？")
_FIRST_TOKEN_STRIP: Final[str] = ",.!?;:()/&+-"
_DIRECT_JOB_REQUEST_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:show me|tell me)\s+(?:new\s+|current\s+|live\s+|some\s+|any\s+)?"
    r"(?:jobs?|roles?|openings?|positions?|vacancies?|matches?)\b"
    r"|^(?:find|find me|search|search for|get|get me|look for|looking for)\b.{0,80}\b"
    r"(?:jobs?|roles?|openings?|positions?|vacancies?|matches?)\b"
    r"|^(?:need|want)\s+(?:a\s+|an\s+|some\s+|any\s+)?(?:job|jobs|role|roles|work)\b",
    re.IGNORECASE,
)


def _is_imperative_job_request(lowered: str) -> bool:
    """Return True for explicit search commands that should stay off the AI path."""
    return bool(_DIRECT_JOB_REQUEST_RE.search(lowered))


def is_open_ended_question(message: str) -> tuple[bool, str]:
    """
    Decide whether a message must route to the conversational AI handler.

    Returns:
        (True, reason): route to ConversationalAIHandler
        (False, "ok"): let the legacy classifier handle it
    """

    text = (message or "").strip()
    if not text:
        return True, "empty"

    lowered = text.lower()

    if any(ch in text for ch in _QUESTION_CHARS):
        return True, "question_mark"

    if _is_imperative_job_request(lowered):
        return False, "ok"

    for phrase in _OPENING_PHRASES:
        if lowered == phrase or lowered.startswith(phrase + " "):
            return True, f"phrase:{phrase.replace(' ', '_')}"

    tokens = lowered.split()
    if not tokens:
        return True, "empty_after_split"

    first = tokens[0].strip(_FIRST_TOKEN_STRIP)
    if first in _OPENING_TOKENS:
        return True, f"token:{first}"

    return False, "ok"
