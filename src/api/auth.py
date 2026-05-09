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

from src.api.rate_limit import LIMIT_LOGIN, limiter
from src.schemas.auth import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse

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

def verify_credentials(email: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user.

    Returns a dict with ``email`` and ``role`` on success, None on failure.

    Lookup order:
    1. users table in DB (when available)
    2. ADMIN_EMAIL / ADMIN_PASSWORD_HASH env vars (backward-compat fallback)
    3. ADMIN_EMAIL / ADMIN_PASSWORD plaintext (dev-only fallback)
    """
    email = email.strip().lower()

    # 1. DB-backed auth
    try:
        from src.repositories.users_repo import get_user_by_email
        user = get_user_by_email(email)
        if user is not None:
            if _PWD_CTX.verify(password, user.password_hash):
                from src.repositories.users_repo import update_last_login
                update_last_login(user.id)
                return {"email": user.email, "role": user.role}
            return None
    except Exception:
        logger.exception("db_auth_error falling_back_to_env_vars")

    # 2. Env-var fallback (single admin; backward-compatible with existing deployments)
    admin_email = os.getenv("ADMIN_EMAIL", "admin@localhost").strip().lower()
    if email != admin_email:
        return None

    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    if password_hash:
        if _PWD_CTX.verify(password, password_hash):
            return {"email": email, "role": "admin"}
        return None

    plaintext = os.getenv("ADMIN_PASSWORD", "").strip()
    if plaintext:
        logger.warning("ADMIN_PASSWORD_HASH not set — using plaintext ADMIN_PASSWORD (dev only)")
        if secrets.compare_digest(password, plaintext):
            return {"email": email, "role": "admin"}
        return None

    logger.error("No admin password configured. Set ADMIN_PASSWORD_HASH in .env.")
    return None


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
@limiter.limit(LIMIT_LOGIN)
def login(request: Request, req: LoginRequest, response: Response) -> LoginResponse:
    user_info = verify_credentials(req.email, req.password)
    if user_info is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user_info["email"], "role": user_info["role"]})
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        max_age=_ttl_hours() * 3600,
    )
    logger.info("login_success email=%r role=%s", user_info["email"], user_info["role"])
    return LoginResponse(message="Logged in", email=user_info["email"])


@router.post("/logout")
def logout(response: Response) -> Dict[str, str]:
    response.delete_cookie(key=_COOKIE_NAME, samesite="strict")
    return {"message": "Logged out"}


@router.get("/me")
def me(request: Request) -> Dict[str, Any]:
    # Deferred import avoids circular dependency (deps imports from this module)
    from src.api.deps import get_current_user
    user = get_current_user(request)
    return {"email": user["email"], "role": user.get("role", "user"), "authenticated": True}


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(request: Request, req: RegisterRequest, response: Response) -> RegisterResponse:
    """
    Create a new user account. Admin-only.

    Requires a valid JWT with role=admin. Password is hashed before storage.
    Returns 409 if the email is already registered.
    """
    from src.api.deps import require_admin
    require_admin(request)

    from src.repositories.users_repo import create_user, get_user_by_email
    if get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = _PWD_CTX.hash(req.password)
    user = create_user(req.email.strip().lower(), password_hash, role=req.role)
    if user is None:
        raise HTTPException(
            status_code=503,
            detail="User registration unavailable — database not connected",
        )

    logger.info("register_success email=%r role=%s", user.email, user.role)
    return RegisterResponse(email=user.email, role=user.role, created=True)
