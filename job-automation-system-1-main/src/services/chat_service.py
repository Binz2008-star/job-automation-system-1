"""
src/services/chat_service.py
Thin service adapter for Rico AI chat, CV parsing, and webhook flows.
Does not modify Rico internals — delegates directly to existing Rico modules
via deferred imports to avoid eager loading of heavy dependencies.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)
_UTC = timezone.utc

# ── Jotform field normalisation ───────────────────────────────────────────────
# Maps raw Jotform label strings (as sent by the form or the Agent "Send API
# Request" test tool) to the snake_case keys that
# rico_jotform_webhook.map_jotform_payload() expects.

_JOTFORM_FIELD_MAP: Dict[str, str] = {
    "Full Name":              "full_name",
    "Name":                   "full_name",
    "Email":                  "email",
    "Email Address":          "email",
    "Phone":                  "phone",
    "Phone Number":           "phone",
    "Telegram Username":      "telegram_username",
    "Target Job Titles":      "target_roles",
    "Target Roles":           "target_roles",
    "Preferred Cities":       "preferred_cities",
    "Preferred Location":     "preferred_cities",
    "Salary Expectation (AED)": "salary_expectation_aed",
    "Minimum Salary (AED)":   "minimum_salary_aed",
    "Skills":                 "skills",
    "Industries":             "industries",
    "Visa Status":            "visa_status",
    "Notice Period":          "notice_period",
    "Years of Experience":    "years_experience",
    "Autonomy Level":         "autonomy_level",
    "Match Strictness":       "match_strictness",
    "Communication Style":    "communication_style",
    "CV Upload":              "cv_upload",
}

# Keys that appear in test/agent payloads but carry no profile data.
_NON_PROFILE_KEYS = frozenset({
    "formID", "form_id", "formId",
    "consent", "ip",
    "submissionID", "submission_id",
})


def _normalize_jotform_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert raw Jotform field labels to snake_case keys.

    If the payload already has a 'pretty' key it is already in the correct
    format; return it unchanged.  Otherwise remap every key using
    _JOTFORM_FIELD_MAP (with a generic fallback of lower().replace(' ', '_')).
    """
    if "pretty" in payload:
        return payload

    normalized: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in _NON_PROFILE_KEYS:
            normalized[key] = value
        else:
            target = _JOTFORM_FIELD_MAP.get(key) or key.lower().replace(" ", "_")
            normalized[target] = value

    return normalized


def _has_user_data(payload: Dict[str, Any]) -> bool:
    """Return True only if a stable unique identifier (email or telegram_username) is present.

    full_name / name are not unique and cannot serve as a user_id, so payloads
    containing only a name are treated as test/agent probes and short-circuited.
    """
    answers = payload.get("pretty", payload)
    return bool(answers.get("email") or answers.get("telegram_username"))


# ── Public service functions ──────────────────────────────────────────────────

def send_message(user_id: str, message: str) -> Dict[str, Any]:
    """Route a chat message through RicoChatAPI and return the response dict.

    RicoChatAPI.process_message → RicoOpenAIAgent.respond handles all provider
    paths (OpenAI, HF free inference, fallback) and _finalize adds the required
    diagnostic metadata (provider, response_source, hf_available, openai_available).
    Never short-circuit to a hardcoded free-mode block — the agent already returns
    the correct fallback text when no keys are present.
    """
    from src.rico_chat_api import RicoChatAPI
    return RicoChatAPI().process_message(user_id=user_id, message=message)


def parse_cv(data: bytes, filename: str = "cv.pdf") -> Dict[str, Any]:
    """Parse CV bytes and return structured ParsedCV dict via CVParser."""
    from src.cv_parser import CVParser
    return CVParser().parse_bytes(data, filename=filename).to_dict()


def handle_telegram_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch an incoming Telegram update to the Rico webhook handler."""
    from src.rico_telegram_webhook import process_telegram_update
    return process_telegram_update(update)


def handle_github_event(event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch an incoming GitHub webhook event.

    Supported events: push, pull_request, issues, ping.
    Unrecognised events are acknowledged but not processed.
    """
    logger.info("github_webhook: event=%s action=%s", event, payload.get("action"))

    if event == "ping":
        return {"status": "ok", "message": "pong", "zen": payload.get("zen", "")}

    if event == "push":
        repo = payload.get("repository", {}).get("full_name", "unknown")
        ref = payload.get("ref", "")
        pusher = payload.get("pusher", {}).get("name", "unknown")
        commits = len(payload.get("commits", []))
        logger.info(
            "github_webhook: push repo=%s ref=%s pusher=%s commits=%d",
            repo, ref, pusher, commits,
        )
        return {"status": "ok", "event": "push", "repo": repo, "ref": ref, "commits": commits}

    if event == "pull_request":
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {}).get("full_name", "unknown")
        logger.info(
            "github_webhook: pull_request action=%s repo=%s pr=%s",
            action, repo, pr.get("number"),
        )
        return {"status": "ok", "event": "pull_request", "action": action, "repo": repo}

    if event == "issues":
        action = payload.get("action", "")
        issue = payload.get("issue", {})
        repo = payload.get("repository", {}).get("full_name", "unknown")
        logger.info(
            "github_webhook: issues action=%s repo=%s issue=%s",
            action, repo, issue.get("number"),
        )
        return {"status": "ok", "event": "issues", "action": action, "repo": repo}

    logger.info("github_webhook: unhandled event=%s — acknowledging", event)
    return {"status": "accepted", "event": event, "message": "Event acknowledged but not processed"}


def handle_jotform_submission(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a Jotform onboarding webhook payload.

    Steps:
      1. Normalise field names (raw Jotform labels → snake_case).
      2. Short-circuit for test/empty payloads that carry no user data —
         returns 'accepted' without touching the DB.
      3. Delegate to the Rico handler for real submissions.
      4. Catch DB errors and return a graceful 'accepted' response so the
         webhook always returns 200 (Jotform retries on non-200).
    """
    normalized = _normalize_jotform_payload(payload)

    if not _has_user_data(normalized):
        logger.info(
            "jotform_webhook: no user data in payload keys=%s — "
            "accepting without DB insert",
            sorted(payload.keys()),
        )
        return {
            "status": "accepted",
            "message": "Webhook reachable, no profile fields provided",
        }

    from src.rico_jotform_webhook import handle_jotform_submission as _handle
    try:
        return _handle(normalized)
    except Exception as exc:
        logger.warning(
            "jotform_webhook: DB write failed (%s: %s) — returning accepted",
            type(exc).__name__, exc,
        )
        return {
            "status": "accepted",
            "message": "Webhook received, profile processing pending",
        }


def get_chat_history(user_id: str, limit: int = 50, before: datetime | None = None) -> list[Dict[str, Any]]:
    """
    Get conversation history for a user with pagination support.

    Args:
        user_id: User identifier
        limit: Maximum number of messages to return (default: 50)
        before: Optional timestamp for pagination (fetch messages before this time)

    Returns:
        List of message dictionaries with role, content, and timestamp
    """
    from src.rico_chat_api import RicoChatAPI
    api = RicoChatAPI()

    # Get messages from memory
    messages = api.memory.get_chat_messages(user_id, limit=limit)

    # Filter by 'before' timestamp if provided
    if before:
        messages = [
            m for m in messages
            if hasattr(m, 'timestamp') and m.timestamp < before
        ]

    # Convert to dict format
    return [
        {
            "role": m.role,
            "content": m.content,
            "timestamp": m.timestamp.isoformat() if hasattr(m, 'timestamp') else None,
        }
        for m in messages
    ]
