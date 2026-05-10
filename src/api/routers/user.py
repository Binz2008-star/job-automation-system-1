"""GET /api/v1/me — current session identity."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

from src.api.deps import get_current_user

router = APIRouter(prefix="/api/v1", tags=["user"])


@router.get("/me")
def me(request: Request) -> Dict[str, Any]:
    user = get_current_user(request)
    return {
        "email":         user["email"],
        "role":          user.get("role", "user"),
        "authenticated": True,
    }
