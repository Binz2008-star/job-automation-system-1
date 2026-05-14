"""src/models/onboarding.py
Server-side onboarding state for a Rico user.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

ONBOARDING_PENDING     = "pending"
ONBOARDING_IN_PROGRESS = "in_progress"
ONBOARDING_COMPLETED   = "completed"

VALID_STATUSES = {ONBOARDING_PENDING, ONBOARDING_IN_PROGRESS, ONBOARDING_COMPLETED}


@dataclass
class OnboardingState:
    user_id: str
    status: str                        # pending | in_progress | completed
    completed_at: Optional[datetime] = None
    updated_at: Optional[datetime]  = None

    def is_complete(self) -> bool:
        return self.status == ONBOARDING_COMPLETED
