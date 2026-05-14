"""Jotform onboarding webhook for Rico AI."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from src.rico_db import RicoDB
from src.repositories.profile_repo import find_identity_candidates
from src.services.identity_flow_mapper import IdentitySignal, map_identity_flow
from src.services.profile_context_resolver import resolve_profile_context

logger = logging.getLogger(__name__)


def _is_production() -> bool:
    """True if any of RICO_ENV / ENV / ENVIRONMENT marks production."""
    for var in ("RICO_ENV", "ENV", "ENVIRONMENT"):
        value = os.getenv(var, "").strip().lower()
        if value in ("production", "prod"):
            return True
    return False


def _validate_webhook_secret() -> bool:
    """Validate that JOTFORM_WEBHOOK_SECRET is set in production."""
    if not _is_production():
        return True

    webhook_secret = os.getenv("JOTFORM_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.warning("jotform_webhook: production mode missing JOTFORM_WEBHOOK_SECRET")
        return False

    return True


def _active_form_ids() -> frozenset:
    """Return accepted Jotform form IDs from JOTFORM_FORM_ID env var."""
    raw = os.getenv("JOTFORM_FORM_ID", "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _resolve_user_id(answers: Dict[str, Any]) -> Optional[str]:
    """Derive a stable, unique user_id. Email preferred; telegram_username is fallback."""
    return answers.get("email") or answers.get("telegram_username") or None


def _build_identity_signal(mapped: Dict[str, Any]) -> IdentitySignal:
    """Build identity signal from a mapped Jotform submission."""
    user = mapped.get("user") or {}
    profile = mapped.get("profile") or {}

    signal_user_id = user.get("external_user_id") or "jotform_pending"

    signal_profile = resolve_profile_context(
        user_id=signal_user_id,
        raw={
            **user,
            **profile,
        },
    )

    return IdentitySignal(
        source="jotform",
        user_id=user.get("external_user_id"),
        telegram_username=user.get("telegram_username"),
        email=user.get("email"),
        phone=user.get("phone"),
        name=user.get("name"),
        profile=signal_profile,
    )


def _identity_resolution_metadata(resolution) -> Dict[str, Any]:
    """Return JSON-safe identity resolution metadata."""
    return {
        "action": resolution.action,
        "confidence": resolution.confidence,
        "matched_user_id": resolution.matched_user_id,
        "reasons": list(resolution.reasons or []),
        "conflicts": {
            key: list(value)
            for key, value in (resolution.conflicts or {}).items()
        },
        "missing_fields": list(resolution.missing_fields or []),
    }


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
        "submission_id": payload.get("submissionID") or payload.get("submission_id"),
    }


def handle_jotform_submission(payload: Dict[str, Any]) -> Dict[str, Any]:
    form_id = (
        payload.get("formID") or payload.get("form_id") or payload.get("formId")
    )
    submission_id = payload.get("submissionID") or payload.get("submission_id")

    if not submission_id:
        logger.warning(
            "jotform_webhook: rejected missing submission_id form_id=%s", form_id
        )
        return {"status": "rejected", "reason": "missing_submission_id"}

    if not _validate_webhook_secret():
        logger.warning(
            "jotform_webhook: rejected missing webhook secret in production form_id=%s submission=%s",
            form_id, submission_id,
        )
        return {"status": "rejected", "reason": "missing_webhook_secret"}

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

    db = RicoDB()
    try:
        first_delivery = db.register_webhook_event(
            provider="jotform",
            submission_id=submission_id,
            form_id=form_id,
            external_user_id=user_id,
            metadata={"form_id": form_id},
        )
    except Exception:
        logger.exception(
            "jotform_webhook: idempotency registration failed form_id=%s submission=%s",
            form_id, submission_id,
        )
        return {"status": "error", "reason": "idempotency_unavailable"}

    if not first_delivery:
        logger.info(
            "jotform_webhook: duplicate submission_id=%s — skipping", submission_id
        )
        return {"status": "ignored", "reason": "duplicate"}

    # Identity resolution: check for existing profiles matching identity signals
    # This runs before user_id check so phone/telegram-only submissions can be resolved
    signal = _build_identity_signal(mapped)
    candidates = find_identity_candidates(signal)
    resolution = map_identity_flow(signal, candidates)
    resolution_meta = _identity_resolution_metadata(resolution)

    logger.info(
        "jotform_webhook: identity resolution submission=%s action=%s confidence=%s matched_user_id=%s",
        submission_id,
        resolution.action,
        resolution.confidence,
        resolution.matched_user_id,
    )

    if resolution.action == "merge" and resolution.matched_user_id:
        user_id = resolution.matched_user_id
        mapped["user"]["external_user_id"] = resolution.matched_user_id
        # Proceed to upsert with matched profile - skip user_id check below
    elif resolution.action == "ask_user":
        db.mark_webhook_event_processed(
            provider="jotform",
            submission_id=submission_id,
            status="pending_identity_confirmation",
            metadata={
                "external_user_id": user_id,
                "identity_resolution": resolution_meta,
            },
        )
        return {
            "status": "accepted",
            "reason": "pending_identity_confirmation",
            "identity_resolution": resolution_meta,
        }

    elif resolution.action == "ignore":
        db.mark_webhook_event_processed(
            provider="jotform",
            submission_id=submission_id,
            status="ignored_identity_signal",
            metadata={
                "external_user_id": user_id,
                "identity_resolution": resolution_meta,
            },
        )
        return {
            "status": "ignored",
            "reason": "weak_identity_signal",
            "identity_resolution": resolution_meta,
        }

    # Only check user_id if identity resolution didn't set it via merge
    if not user_id:
        logger.info(
            "jotform_webhook: no stable user_id in submission=%s — skipping DB write",
            submission_id,
        )
        db.mark_webhook_event_processed(
            provider="jotform",
            submission_id=submission_id,
            status="ignored_missing_user",
        )
        return {"status": "accepted", "message": "No identifiable user field provided"}

    logger.info(
        "jotform_webhook: processing form_id=%s submission=%s user_id=%s consent=%s",
        mapped.get("form_id"), mapped.get("submission_id"), user_id, mapped.get("consent"),
    )

    user = db.upsert_user(mapped["user"])
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

    db.mark_webhook_event_processed(
        provider="jotform",
        submission_id=submission_id,
        user_id=db_user_id,
        status="processed",
        metadata={"external_user_id": user_id},
    )
    logger.info(
        "jotform_webhook: ok form_id=%s submission=%s db_user_id=%s",
        mapped.get("form_id"), mapped.get("submission_id"), db_user_id,
    )
    return {"status": "ok", "user_id": db_user_id}
