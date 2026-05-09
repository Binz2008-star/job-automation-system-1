"""
src/api/auth.py
JWT authentication: login / logout endpoints + token utilities.

Config (env vars):
  ADMIN_EMAIL           — login email (default: admin@localhost)
  ADMIN_PASSWORD_HASH   — bcrypt hash: passlib.hash.bcrypt.hash("your-password")
  ADMIN_PASSWORD        — plaintext fallback when hash is absent (dev only)
  JWT_SECRET            — HS256 signing secret (32+ bytes recommended)
  JWT_TTL_HOURS         — token lifetime in hours (default: 24)
  COOKIE_SECURE         — set "true" in production (HTTPS only cookie)

Token stored as an httpOnly, SameSite=strict cookie named "access_token".
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.schemas.auth import LoginRequest, LoginResponse

logger = logging.getLogger(__name__)

_PWD_CTX = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGORITHM = "HS256"
_COOKIE_NAME = "access_token"


# ── Config helpers ────────────────────────────────────────────────────────────

def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        if not hasattr(_jwt_secret, "_ephemeral"):
            _jwt_secret._ephemeral = secrets.token_hex(32)  # type: ignore[attr-defined]
            logger.warning(
                "JWT_SECRET is not set — using an ephemeral secret. "
                "Sessions will not survive process restarts. "
                "Set JWT_SECRET in .env before deploying."
            )
        return _jwt_secret._ephemeral  # type: ignore[attr-defined]
    return secret


def _ttl_hours() -> int:
    try:
        return int(os.getenv("JWT_TTL_HOURS", "24"))
    except ValueError:
        return 24


# ── Credential check ─────────────────────────────────────────────────────────

def verify_credentials(email: str, password: str) -> bool:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@localhost").strip().lower()
    if email.strip().lower() != admin_email:
        return False

    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    if password_hash:
        return _PWD_CTX.verify(password, password_hash)

    plaintext = os.getenv("ADMIN_PASSWORD", "").strip()
    if plaintext:
        logger.warning(
            "ADMIN_PASSWORD_HASH not set — using plaintext ADMIN_PASSWORD (dev only)"
        )
        return secrets.compare_digest(password, plaintext)

    logger.error("No admin password configured. Set ADMIN_PASSWORD_HASH in .env.")
    return False


# ── Token utilities ───────────────────────────────────────────────────────────

def create_access_token(data: Dict[str, Any]) -> str:
    payload = dict(data)
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=_ttl_hours())
    return jwt.encode(payload, _jwt_secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_ALGORITHM])
    except JWTError:
        return None


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, response: Response) -> LoginResponse:
    if not verify_credentials(req.email, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": req.email.strip().lower()})
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        max_age=_ttl_hours() * 3600,
    )
    logger.info("login_success email=%r", req.email)
    return LoginResponse(message="Logged in", email=req.email.strip().lower())


@router.post("/logout")
def logout(response: Response) -> Dict[str, str]:
    response.delete_cookie(key=_COOKIE_NAME, samesite="strict")
    return {"message": "Logged out"}


@router.get("/me")
def me(request: Request) -> Dict[str, Any]:
    # Deferred import avoids circular dependency (deps imports from this module)
    from src.api.deps import get_current_user
    user = get_current_user(request)
    return {"email": user["email"], "authenticated": True}
