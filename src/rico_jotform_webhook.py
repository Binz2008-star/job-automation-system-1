"""Jotform onboarding webhook for Rico AI."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from src.rico_db import RicoDB

logger = logging.getLogger(__name__)

_SEEN_SUBMISSIONS_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "rico" / "_seen_submissions.json"
)


def _load_seen_submissions() -> set:
    try:
        if _SEEN_SUBMISSIONS_FILE.exists():
            return set(json.loads(_SEEN_SUBMISSIONS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return set()


def _mark_submission_seen(submission_id: str) -> None:
    if not submission_id or submission_id == "?":
        return
    seen = _load_seen_submissions()
    seen.add(submission_id)
    _SEEN_SUBMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SEEN_SUBMISSIONS_FILE.write_text(
        json.dumps(sorted(seen)[-10_000:], ensure_ascii=False),
        encoding="utf-8",
    )


def _is_duplicate_submission(submission_id: str) -> bool:
    if not submission_id or submission_id == "?":
        return False
    return submission_id in _load_seen_submissions()


def _is_production() -> bool:
    return os.getenv("RICO_ENV", os.getenv("ENV", "")).lower() in ("production", "prod")


def _active_form_ids() -> frozenset:
    """Return accepted Jotform form IDs from JOTFORM_FORM_ID env var.

    Supports comma-separated values for multi-form setups.
    Returns an empty frozenset when the var is unset — disables validation (dev only).
    In production (RICO_ENV=production) an empty frozenset causes fail-closed behaviour
    handled by handle_jotform_submission.
    """
    raw = os.getenv("JOTFORM_FORM_ID", "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _resolve_user_id(answers: Dict[str, Any]) -> Optional[str]:
    """Derive a stable, unique user_id. Email preferred; telegram_username is fallback.

    full_name is intentionally excluded — it is not unique and cannot be a user_id.
    """
    return answers.get("email") or answers.get("telegram_username") or None


def map_jotform_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    answers = payload.get("pretty", payload)
    user_id = _resolve_user_id(answers)

    return {
        "user": {
            "external_user_id": user_id,
            "name": answers.get("full_name") or answers.get("name"),
            "email": answers.get("email"),
            "phone": answers.get("phone"),
            "telegram_username": answers.get("telegram_username"),
        },
        "profile": {
            "target_roles": answers.get("target_roles"),
            "preferred_cities": answers.get("preferred_cities"),
            "salary_expectation_aed": answers.get("salary_expectation_aed"),
            "minimum_salary_aed": answers.get("minimum_salary_aed"),
            "skills": answers.get("skills"),
            "industries": answers.get("industries"),
            "visa_status": answers.get("visa_status"),
            "notice_period": answers.get("notice_period"),
            "years_experience": answers.get("years_experience"),
        },
        "settings": {
            "autonomy_level": answers.get("autonomy_level"),
            "match_strictness": answers.get("match_strictness"),
            "communication_style": answers.get("communication_style"),
        },
        "cv_file_url": answers.get("cv_upload"),
        "consent": bool(answers.get("consent")),
        "form_id": payload.get("formID") or payload.get("form_id") or payload.get("formId"),
        "submission_id": payload.get("submissionID") or payload.get("submission_id", "?"),
    }


def handle_jotform_submission(payload: Dict[str, Any]) -> Dict[str, Any]:
    form_id = (
        payload.get("formID") or payload.get("form_id") or payload.get("formId")
    )
    submission_id = payload.get("submissionID") or payload.get("submission_id", "?")

    # ── Idempotency — reject replayed submissions ──────────────────────────────
    if _is_duplicate_submission(submission_id):
        logger.info(
            "jotform_webhook: duplicate submission_id=%s — skipping", submission_id
        )
        return {"status": "accepted", "message": "Duplicate submission ignored"}

    # ── Form ID validation ─────────────────────────────────────────────────────
    active_ids = _active_form_ids()
    if not active_ids and _is_production():
        logger.error(
            "jotform_webhook: JOTFORM_FORM_ID not configured in production — rejecting submission=%s",
            submission_id,
        )
        return {"status": "rejected", "reason": "form_id_not_configured"}
    if active_ids and form_id not in active_ids:
        logger.warning(
            "jotform_webhook: rejected unknown form_id=%s submission=%s",
            form_id, submission_id,
        )
        return {"status": "rejected", "reason": "unknown_form_id"}

    mapped = map_jotform_payload(payload)
    user_id = mapped["user"].get("external_user_id")

    # No stable user_id — cannot create a meaningful DB record.
    if not user_id:
        logger.info(
            "jotform_webhook: no stable user_id in submission=%s — skipping DB write",
            submission_id,
        )
        return {"status": "accepted", "message": "No identifiable user field provided"}

    logger.info(
        "jotform_webhook: processing form_id=%s submission=%s user_id=%s consent=%s",
        mapped.get("form_id"), mapped.get("submission_id"), user_id, mapped.get("consent"),
    )

    # ── DB writes — profile/settings failures are isolated ────────────────────
    db = RicoDB()
    user = db.upsert_user(mapped["user"])   # raises on failure — caught by chat_service
    db_user_id = str(user["id"])

    try:
        db.upsert_profile(db_user_id, mapped["profile"], cv_file_url=mapped.get("cv_file_url"))
    except Exception as exc:
        logger.error(
            "jotform_webhook: upsert_profile failed db_user_id=%s: %s", db_user_id, exc
        )

    try:
        db.upsert_settings(db_user_id, mapped["settings"])
    except Exception as exc:
        logger.error(
            "jotform_webhook: upsert_settings failed db_user_id=%s: %s", db_user_id, exc
        )

    # ── Consent → mark onboarding complete ────────────────────────────────────
    if mapped.get("consent"):
        try:
            from src.repositories.onboarding_repo import mark_onboarding_complete
            mark_onboarding_complete(user_id)
            logger.info(
                "jotform_webhook: onboarding marked complete user_id=%s", user_id
            )
        except Exception as exc:
            logger.warning(
                "jotform_webhook: mark_onboarding_complete failed user_id=%s: %s",
                user_id, exc,
            )

    _mark_submission_seen(submission_id)
    logger.info(
        "jotform_webhook: ok form_id=%s submission=%s db_user_id=%s",
        mapped.get("form_id"), mapped.get("submission_id"), db_user_id,
    )
    return {"status": "ok", "user_id": db_user_id}
