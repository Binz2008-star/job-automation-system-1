from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_id
from src.schemas.subscription import SubscriptionResponse
from src.subscription_plans import resolve_effective_user_plan

router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])


@router.get("/me", response_model=SubscriptionResponse)
def get_my_subscription(user_id: str = Depends(get_current_user_id)) -> SubscriptionResponse:
    return resolve_effective_user_plan(user_id)
