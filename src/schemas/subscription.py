"""Pydantic schemas for Rico subscription plans and read-only subscription state."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SubscriptionTier(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    TRIALING = "trialing"
    EXPIRED = "expired"


class SubscriptionPlan(BaseModel):
    id: str
    tier: SubscriptionTier
    name: str
    price_monthly: float
    price_yearly: float
    currency: str = "USD"
    features: List[str]
    limits: Dict[str, Any]
    is_popular: bool = False
    description: Optional[str] = None


class UserSubscription(BaseModel):
    user_id: str
    plan_tier: SubscriptionTier
    status: SubscriptionStatus
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    current_period_start: datetime
    current_period_end: datetime
    cancel_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    features_enabled: Dict[str, bool] = Field(default_factory=dict)
    usage_limits: Dict[str, int] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SubscriptionCreateRequest(BaseModel):
    tier: SubscriptionTier
    billing_cycle: Literal["monthly", "yearly"] = "monthly"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class SubscriptionResponse(BaseModel):
    subscription: UserSubscription
    plan: SubscriptionPlan
    is_active: bool


class UsageCheckResponse(BaseModel):
    allowed: bool
    remaining: Optional[int] = None
    limit: Optional[int] = None
    message: Optional[str] = None


class WebhookEvent(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]
