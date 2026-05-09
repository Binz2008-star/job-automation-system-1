"""
src/api/deps.py
FastAPI dependency injection for authentication.
Import get_current_user as a Depends() argument on protected routes.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException, Request

from src.api.auth import decode_access_token


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Validate the JWT cookie. Raises HTTP 401 if missing or invalid.
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
    return {"email": payload["sub"]}
