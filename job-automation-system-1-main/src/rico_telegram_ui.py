"""
src/rico_telegram_ui.py
Telegram UI helpers for Rico AI.

Provides inline keyboard structures, callback parsing, job caching,
and callback action dispatch without changing the existing notification pipeline.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from filelock import FileLock, Timeout as FileLockTimeout

from src.applications import get_job_id

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

TELEGRAM_ACTIONS_FILE = DATA_DIR / "telegram_actions.json"
TELEGRAM_ACTIONS_LOCK = str(TELEGRAM_ACTIONS_FILE) + ".lock"

TELEGRAM_JOB_CACHE_FILE = DATA_DIR / "telegram_job_cache.json"
TELEGRAM_JOB_CACHE_LOCK = str(TELEGRAM_JOB_CACHE_FILE) + ".lock"

LOCK_TIMEOUT = 10
_CACHE_TTL_DAYS = 30


RICO_ACTIONS = [
    ("Apply",        "apply"),
    ("Save",         "save"),
    ("Skip",         "skip"),
    ("Why this?",    "why"),
    ("Draft",        "draft"),
    ("Remind me",    "remind"),
    ("Not relevant", "not_relevant"),
]

SUPPORTED_ACTIONS = {action for _, action in RICO_ACTIONS}


# ─── Keyboard builders ────────────────────────────────────────────────────────

def recommendation_keyboard(job_key: str) -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Apply", "callback_data": f"rico:apply:{job_key}"},
                {"text": "Save",  "callback_data": f"rico:save:{job_key}"},
                {"text": "Skip",  "callback_data": f"rico:skip:{job_key}"},
            ],
            [
                {"text": "Why this?", "callback_data": f"rico:why:{job_key}"},
                {"text": "Draft",     "callback_data": f"rico:draft:{job_key}"},
            ],
            [
                {"text": "Remind me",    "callback_data": f"rico:remind:{job_key}"},
                {"text": "Not relevant", "callback_data": f"rico:not_relevant:{job_key}"},
            ],
        ]
    }


def recommendation_keyboard_for_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return recommendation_keyboard(get_job_id(job))


def recommendation_message(job: Dict[str, Any]) -> str:
    title = job.get("title") or "Role"
    company = job.get("company") or "Company"
    location = job.get("location") or "UAE"
    score = job.get("rico_score") or job.get("score") or "-"
    explanation = (
        job.get("rico_explanation")
        or job.get("why")
        or "Strong potential fit based on your profile."
    )
    return (
        f"🔥 {title}\n"
        f"🏢 {company}\n"
        f"📍 {location}\n"
        f"🎯 Match: {score}%\n\n"
        f"Why Rico picked this:\n{explanation}"
    )


# ─── Job cache (populated when cards are sent) ────────────────────────────────

def cache_job(job: Dict[str, Any]) -> None:
    """Store a job dict by its key so callbacks can look up full details."""
    job_key = get_job_id(job)
    entry = {**job, "_cached_at": datetime.now().isoformat()}
    try:
        with FileLock(TELEGRAM_JOB_CACHE_LOCK, timeout=LOCK_TIMEOUT):
            cache = _load_job_cache()
            cutoff = (datetime.now() - timedelta(days=_CACHE_TTL_DAYS)).isoformat()
            cache = {k: v for k, v in cache.items() if v.get("_cached_at", "") >= cutoff}
            cache[job_key] = entry
            _save_job_cache(cache)
    except FileLockTimeout:
        logger.warning("cache_job_lock_timeout job_key=%s", job_key)


def lookup_job(job_key: str) -> Optional[Dict[str, Any]]:
    """Return the cached job dict for this key, or None."""
    try:
        return _load_job_cache().get(job_key)
    except Exception:
        return None


def _load_job_cache() -> Dict[str, Any]:
    try:
        with TELEGRAM_JOB_CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_job_cache(cache: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TELEGRAM_JOB_CACHE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    os.replace(tmp, TELEGRAM_JOB_CACHE_FILE)


# ─── Callback parsing ─────────────────────────────────────────────────────────

def parse_callback(callback_data: str) -> Dict[str, str]:
    parts = (callback_data or "").split(":", 2)
    if len(parts) != 3:
        return {"namespace": "unknown", "action": "unknown", "job_key": ""}
    namespace, action, job_key = parts
    return {"namespace": namespace, "action": action, "job_key": job_key}


# ─── Action log ───────────────────────────────────────────────────────────────

def record_callback_action(
    action: str,
    job_key: str,
    user_id: str = "",
    metadata: Dict[str, Any] | None = None,
) -> bool:
    if action not in SUPPORTED_ACTIONS:
        return False
    entry = {
        "action": action,
        "job_key": job_key,
        "user_id": user_id,
        "metadata": metadata or {},
        "created_at": datetime.now().isoformat(),
    }
    try:
        with FileLock(TELEGRAM_ACTIONS_LOCK, timeout=LOCK_TIMEOUT):
            entries = _load_action_log()
            entries.append(entry)
            _save_action_log(entries)
        return True
    except FileLockTimeout:
        logger.warning("record_callback_action_lock_timeout")
        return False


def _load_action_log() -> List[Dict[str, Any]]:
    try:
        with TELEGRAM_ACTIONS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_action_log(entries: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TELEGRAM_ACTIONS_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp, TELEGRAM_ACTIONS_FILE)


# ─── Callback dispatch ────────────────────────────────────────────────────────

def handle_callback_only(update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a Telegram callback_query update.
    Looks up the full job from cache, dispatches to handle_job_action,
    and returns a result dict that includes callback_id for answerCallbackQuery.
    """
    callback = update.get("callback_query", {}) if isinstance(update, dict) else {}
    data = parse_callback(callback.get("data", ""))
    user = callback.get("from", {}) or {}
    user_id = str(user.get("id") or "")
    callback_id = callback.get("id", "")

    if data["namespace"] != "rico" or data["action"] not in SUPPORTED_ACTIONS:
        return {
            "ok": False,
            "chat_id": user_id,
            "callback_id": callback_id,
            "reply": "Unsupported action.",
        }

    job = lookup_job(data["job_key"]) or {"id": data["job_key"]}
    result = handle_job_action(data["action"], job, user_id=user_id)

    return {
        "ok": True,
        "chat_id": user_id,
        "callback_id": callback_id,
        "reply": result.get("reply", callback_ack_message(data["action"])),
        "action": data["action"],
        "job_key": data["job_key"],
    }


def callback_ack_message(action: str) -> str:
    return {
        "apply":        "Apply noted. Rico will track this job.",
        "save":         "Saved. Rico will keep this in mind.",
        "skip":         "Skipped. Rico will use this as feedback.",
        "why":          "Rico picked this based on your profile and search preferences.",
        "draft":        "Draft requested. Rico will prepare a message when job details are available.",
        "remind":       "Reminder noted.",
        "not_relevant": "Marked not relevant. Rico will reduce similar matches.",
    }.get(action, "Action received.")


def handle_job_action(action: str, job: Dict[str, Any], user_id: str = "") -> Dict[str, Any]:
    """
    Dispatch a job action through the agent runtime.
    Telegram is the UI layer; all business logic lives in the runtime.
    """
    from src.agent.runtime import agent_runtime
    job_key = get_job_id(job)
    result = agent_runtime.handle_action(
        user_id=user_id,
        action=action,
        job_key=job_key,
        job=job,
        source="telegram",
    )
    return {"ok": result.ok, "reply": result.message}
