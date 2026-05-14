"""
src/api/routers/onboarding.py

POST /api/v1/onboarding/submit — persist structured onboarding answers directly
to the user profile via upsert_profile(). Bypasses NLP round-trip; the frontend
collects answers in structured form so there is no need to parse natural language.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


class OnboardingSubmitRequest(BaseModel):
    target_roles: Optional[List[str]] = Field(default=None)
    preferred_cities: Optional[List[str]] = Field(default=None)
    salary_expectation_aed: Optional[float] = Field(default=None, ge=0)
    years_experience: Optional[float] = Field(default=None, ge=0)
    current_role: Optional[str] = Field(default=None, max_length=200)
    skills: Optional[List[str]] = Field(default=None)


@router.post("/submit")
def onboarding_submit(request: Request, body: OnboardingSubmitRequest) -> Dict[str, Any]:
    user = get_current_user(request)
    user_id: str = user["email"]

    updates: Dict[str, Any] = {}
    if body.target_roles is not None:
        updates["target_roles"] = [r.strip() for r in body.target_roles if r.strip()]
    if body.preferred_cities is not None:
        updates["preferred_cities"] = [c.strip() for c in body.preferred_cities if c.strip()]
    if body.salary_expectation_aed is not None:
        updates["salary_expectation_aed"] = body.salary_expectation_aed
    if body.years_experience is not None:
        updates["years_experience"] = body.years_experience
    if body.current_role is not None:
        updates["current_role"] = body.current_role.strip()
    if body.skills is not None:
        updates["skills"] = [s.strip() for s in body.skills if s.strip()]

    if updates:
        from src.repositories.profile_repo import upsert_profile
        upsert_profile(user_id, updates)
        logger.info("onboarding_submit: profile updated user_id=%s fields=%s", user_id, list(updates.keys()))
    else:
        logger.info("onboarding_submit: no fields to update user_id=%s", user_id)

    return {"status": "ok", "updated_fields": list(updates.keys())}
