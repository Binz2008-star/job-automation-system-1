"""Jotform onboarding webhook for Rico AI."""

from __future__ import annotations

from typing import Any, Dict

from src.rico_db import RicoDB


def map_jotform_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    answers = payload.get("pretty", payload)

    return {
        "user": {
            "external_user_id": answers.get("email") or answers.get("telegram_username") or answers.get("full_name"),
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
    }


def handle_jotform_submission(payload: Dict[str, Any]) -> Dict[str, Any]:
    db = RicoDB()
    mapped = map_jotform_payload(payload)

    user = db.upsert_user(mapped["user"])
    db.upsert_profile(user["id"], mapped["profile"], cv_file_url=mapped.get("cv_file_url"))
    db.upsert_settings(user["id"], mapped["settings"])

    return {
        "status": "ok",
        "user_id": str(user["id"]),
    }
