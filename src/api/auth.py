"""
src/api/auth.py
JWT authentication: login / logout endpoints + token utilities.

Config (env vars):
  ADMIN_EMAIL           — login email (default: admin@localhost)
  ADMIN_PASSWORD_HASH   — bcrypt hash: bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
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

import bcrypt as _bcrypt
from fastapi import APIRouter, HTTPException, Request, Response
from jose import JWTError, jwt

from src.api.rate_limit import LIMIT_LOGIN, limiter
from src.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_COOKIE_NAME = "access_token"


def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt(12)).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


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
    _db_error = False
    try:
        from src.repositories.users_repo import get_user_by_email
        user = get_user_by_email(email)
        if user is not None:
            if _verify_password(password, user.password_hash):
                from src.repositories.users_repo import update_last_login
                update_last_login(user.id)
                return {"email": user.email, "role": user.role}
            return None
    except Exception:
        _db_error = True
        logger.exception("db_auth_error falling_back_to_env_vars")

    # In production, never silently fall back to env-var auth on a DB error.
    # Set ALLOW_ENV_AUTH_FALLBACK=true to override during an incident.
    _env = os.getenv("RICO_ENV", os.getenv("ENV", "")).lower()
    _is_prod = _env in ("production", "prod")
    _fallback_allowed = os.getenv("ALLOW_ENV_AUTH_FALLBACK", "").lower() in ("1", "true", "yes")
    if _db_error and _is_prod and not _fallback_allowed:
        logger.error("db_auth_error in production — env fallback disabled; rejecting login for %r", email)
        return None

    # 2. Env-var fallback (single admin; backward-compatible with existing deployments)
    admin_email = os.getenv("ADMIN_EMAIL", "admin@localhost").strip().lower()
    if email != admin_email:
        return None

    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    if password_hash:
        if _verify_password(password, password_hash):
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
    _secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        # SameSite=None;Secure allows cross-origin cookie sending (required when
        # the frontend and API are on different origins, e.g. localhost vs Render).
        # SameSite=Lax is used in local dev (COOKIE_SECURE=false) where Secure
        # cookies cannot be set over plain HTTP.
        samesite="none" if _secure else "lax",
        secure=_secure,
        max_age=_ttl_hours() * 3600,
    )
    logger.info("login_success email=%r role=%s", user_info["email"], user_info["role"])
    return LoginResponse(message="Logged in", email=user_info["email"])


@router.post("/logout")
def logout(response: Response) -> Dict[str, str]:
    _secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    response.delete_cookie(
        key=_COOKIE_NAME,
        samesite="none" if _secure else "lax",
        secure=_secure,
    )
    return {"message": "Logged out"}


@router.get("/me")
def me(request: Request) -> Dict[str, Any]:
    # Deferred import avoids circular dependency (deps imports from this module)
    from src.api.deps import get_current_user
    user = get_current_user(request)
    return {"email": user["email"], "role": user.get("role", "user"), "authenticated": True}


def _reset_base_url() -> str:
    return os.getenv("RESET_BASE_URL", "http://localhost:3000").rstrip("/")


def _is_production() -> bool:
    env = os.getenv("RICO_ENV", os.getenv("ENV", "")).lower()
    return env in ("production", "prod")


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(req: ForgotPasswordRequest) -> ForgotPasswordResponse:
    """
    Initiate password reset. Always returns generic success to prevent email enumeration.
    Dev/local: logs reset URL to stdout.
    Production: token suppressed unless RESET_TOKEN_LOG=true.
    """
    from src.repositories.password_reset_repo import create_reset_token
    from src.repositories.users_repo import get_user_by_email

    _generic = ForgotPasswordResponse(
        message="If that email is registered, a reset link has been sent."
    )
    email = req.email.strip().lower()
    user  = get_user_by_email(email)
    if user is None:
        logger.info("password_reset_request email=%r user_not_found", email)
        return _generic

    try:
        token = create_reset_token(email)
    except Exception:
        logger.exception("password_reset_token_creation_failed email=%r", email)
        return _generic

    reset_url    = f"{_reset_base_url()}/reset-password?token={token}"
    _prod        = _is_production()
    _token_log   = os.getenv("RESET_TOKEN_LOG", "").lower() in ("1", "true", "yes")

    if not _prod or _token_log:
        logger.info("password_reset_url email=%r url=%s", email, reset_url)
    else:
        logger.info(
            "password_reset_requested email=%r (token suppressed in production)",
            email,
        )

    return _generic


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(req: ResetPasswordRequest) -> ResetPasswordResponse:
    """Validate the reset token and set a new password."""
    from src.repositories.password_reset_repo import consume_reset_token
    from src.repositories.users_repo import update_password

    email = consume_reset_token(req.token)
    if email is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid, expired, or already used reset token",
        )

    new_hash = _hash_password(req.new_password)
    ok = update_password(email, new_hash)
    if not ok:
        logger.error("password_reset_update_failed email=%r", email)
        raise HTTPException(
            status_code=503,
            detail="Password update failed — please try again",
        )

    logger.info("password_reset_success email=%r", email)
    return ResetPasswordResponse(
        message="Password updated. You can now sign in with your new password."
    )


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

    password_hash = _hash_password(req.password)
    user = create_user(req.email.strip().lower(), password_hash, role=req.role)
    if user is None:
        raise HTTPException(
            status_code=503,
            detail="User registration unavailable — database not connected",
        )

    logger.info("register_success email=%r role=%s", user.email, user.role)
    return RegisterResponse(email=user.email, role=user.role, created=True)
