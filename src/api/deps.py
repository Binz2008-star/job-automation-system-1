"""
src/api/deps.py
FastAPI dependency injection for authentication and authorization.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException, Request

from src.api.auth import decode_access_token


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Validate the JWT cookie. Raises HTTP 401 if missing or invalid.
    Returns dict with ``email`` and ``role`` (defaults to "user" for legacy tokens).
    Usage: route(user: dict = Depends(get_current_user))
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. POST /api/v1/auth/login first.",
        )
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {
        "email": payload["sub"],
        "role":  payload.get("role", "user"),   # legacy tokens have no role → default "user"
    }


def require_admin(request: Request) -> Dict[str, Any]:
    """
    Validate the JWT cookie AND require role=admin. Raises 401/403 otherwise.
    Usage: route(user: dict = Depends(require_admin))
         or inline: require_admin(request)
    """
    user = get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
