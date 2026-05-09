"""Telegram UI helpers for Rico AI.

Provides inline keyboard structures and consistent recommendation cards without
changing the existing Telegram notification pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List


RICO_ACTIONS = [
    ("Apply Now", "apply"),
    ("Save", "save"),
    ("Ignore", "ignore"),
    ("See Details", "details"),
    ("Write Cover Letter", "cover_letter"),
    ("Prepare Interview", "interview"),
]


def recommendation_keyboard(job_key: str) -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": f"rico:{action}:{job_key}"}]
            for text, action in RICO_ACTIONS
        ]
    }


def recommendation_message(match: Dict[str, Any]) -> str:
    title = match.get("title") or "Role"
    company = match.get("company") or "Company"
    location = match.get("location") or "UAE"
    score = match.get("rico_score") or match.get("score") or "-"
    explanation = match.get("rico_explanation") or match.get("why") or "Strong potential fit based on your profile."

    return (
        f"🔥 {title}\n"
        f"🏢 {company}\n"
        f"📍 {location}\n"
        f"🎯 Match: {score}%\n\n"
        f"Why Rico picked this:\n{explanation}"
    )


def parse_callback(callback_data: str) -> Dict[str, str]:
    parts = (callback_data or "").split(":", 2)
    if len(parts) != 3:
        return {"namespace": "unknown", "action": "unknown", "job_key": ""}
    namespace, action, job_key = parts
    return {
        "namespace": namespace,
        "action": action,
        "job_key": job_key,
    }
