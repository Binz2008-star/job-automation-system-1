"""src/agent/identity/resolver.py

Canonical identity resolver for Rico agent.

Resolves user identity from multiple sources into a single canonical user_id:
- Guest public sessions (public:*)
- Authenticated JWT users (email)
- Jotform submissions (email or telegram_username)
- Telegram users (chat_id)
- CV-extracted identity (email from parsed CV)

All identity sources merge into one canonical user record.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.db import get_db_connection
from src.repositories.profile_repo import get_profile, upsert_profile
from src.repositories.audit_repo import log_identity_resolution, log_identity_merge, log_identity_link

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PUBLIC_SESSION_PREFIX = "public:"


@dataclass
class IdentityResolution:
    """Result of identity resolution."""
    canonical_user_id: str
    identity_source: str  # "guest", "authenticated", "jotform", "telegram", "cv"
    confidence: float  # 0.0-1.0
    merged: bool  # True if this identity was merged with an existing user
    existing_profile: bool  # True if profile already exists for this user
    metadata: Dict[str, Any]  # Additional context about the resolution


class IdentityResolver:
    """
    Resolves and merges user identities from multiple sources.

    Priority for canonical user_id:
    1. Email (highest confidence) - from JWT, Jotform, or CV
    2. Telegram username - from Jotform or Telegram webhook
    3. Telegram chat_id - from Telegram webhook
    4. Guest session ID - from public chat (lowest confidence)
    """

    def __init__(self):
        self._cache: Dict[str, IdentityResolution] = {}

    def resolve(
        self,
        *,
        email: Optional[str] = None,
        telegram_username: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        session_id: Optional[str] = None,
        jotform_submission: Optional[Dict[str, Any]] = None,
        cv_extracted_email: Optional[str] = None,
        is_jwt: bool = False,
    ) -> IdentityResolution:
        """
        Resolve canonical user_id from provided identity signals.

        Args:
            email: User email from JWT, Jotform, or CV
            telegram_username: Telegram handle from Jotform or Telegram
            telegram_chat_id: Numeric Telegram chat ID from webhook
            session_id: Guest session ID for public chat
            jotform_submission: Full Jotform submission payload
            cv_extracted_email: Email extracted from CV parsing
            is_jwt: Explicit flag indicating JWT-authenticated context

        Returns:
            IdentityResolution with canonical user_id and resolution metadata
        """
        # Extract email from Jotform if provided
        if jotform_submission and not email:
            email = self._extract_email_from_jotform(jotform_submission)
            telegram_username = telegram_username or self._extract_telegram_from_jotform(jotform_submission)

        # Use CV-extracted email if no other email
        if cv_extracted_email and not email:
            email = cv_extracted_email

        # Determine identity source and canonical user_id
        if email:
            canonical_user_id = email.lower().strip()
            identity_source = "authenticated" if is_jwt else "jotform" if jotform_submission else "cv"
            confidence = 0.95
        elif telegram_username:
            canonical_user_id = f"telegram:{telegram_username.lstrip('@')}"
            identity_source = "telegram"
            confidence = 0.85
        elif telegram_chat_id:
            canonical_user_id = f"telegram_chat:{telegram_chat_id}"
            identity_source = "telegram"
            confidence = 0.80
        elif session_id:
            canonical_user_id = f"{_PUBLIC_SESSION_PREFIX}{session_id}"
            identity_source = "guest"
            confidence = 0.30
        else:
            # Fallback: generate a stable guest ID
            import uuid
            canonical_user_id = f"{_PUBLIC_SESSION_PREFIX}{uuid.uuid4().hex[:16]}"
            identity_source = "guest"
            confidence = 0.20

        # Check for existing profile (indicates this identity has been seen before)
        existing_profile = get_profile(canonical_user_id) is not None

        # Check for potential identity merge (e.g., guest session later authenticates)
        merged = False
        if not existing_profile and email:
            # Check if this email matches any existing telegram or guest users
            merged = self._attempt_identity_merge(canonical_user_id, email)

        metadata = {
            "email": email,
            "telegram_username": telegram_username,
            "telegram_chat_id": telegram_chat_id,
            "session_id": session_id,
            "has_jotform": bool(jotform_submission),
            "has_cv_email": bool(cv_extracted_email),
        }

        resolution = IdentityResolution(
            canonical_user_id=canonical_user_id,
            identity_source=identity_source,
            confidence=confidence,
            merged=merged,
            existing_profile=existing_profile,
            metadata=metadata,
        )

        # Cache the resolution
        self._cache[canonical_user_id] = resolution

        logger.info(
            "identity_resolved canonical=%s source=%s confidence=%.2f merged=%s existing=%s",
            canonical_user_id,
            identity_source,
            confidence,
            merged,
            existing_profile,
        )

        # Log identity resolution for audit trail
        log_identity_resolution(
            canonical_user_id=canonical_user_id,
            identity_source=identity_source,
            confidence=confidence,
            metadata=metadata,
        )

        return resolution

    def _extract_email_from_jotform(self, submission: Dict[str, Any]) -> Optional[str]:
        """Extract email from Jotform submission."""
        answers = submission.get("pretty", submission)
        email = answers.get("email") or answers.get("Email Address") or answers.get("Email")
        if email:
            email_match = _EMAIL_RE.search(str(email))
            return email_match.group(0) if email_match else None
        return None

    def _extract_telegram_from_jotform(self, submission: Dict[str, Any]) -> Optional[str]:
        """Extract Telegram username from Jotform submission."""
        answers = submission.get("pretty", submission)
        telegram = answers.get("telegram_username") or answers.get("Telegram Username")
        if telegram:
            return str(telegram).lstrip("@")
        return None

    def _is_jwt_context(self, is_jwt: bool = False) -> bool:
        """Detect if we're in a JWT-authenticated context.

        Args:
            is_jwt: Explicit flag from caller indicating JWT context

        Returns:
            True if in JWT context, False otherwise
        """
        return is_jwt

    def _attempt_identity_merge(self, canonical_user_id: str, email: str) -> bool:
        """
        Attempt to merge this identity with existing users.

        If a guest session or telegram user later provides an email,
        merge their data under the email as the canonical ID.
        """
        try:
            conn = get_db_connection()
            if not conn:
                return False

            with conn.cursor() as cur:
                # Check for existing users with this email
                cur.execute(
                    "SELECT id, external_user_id FROM rico_users WHERE email = %s",
                    (email.lower(),),
                )
                existing = cur.fetchone()

                if existing:
                    # User already exists with this email - no merge needed
                    conn.close()
                    return False

                # Check for telegram users that might match this email
                # This would require additional cross-reference tables
                # For now, we'll skip automatic merging

            conn.close()
            return False
        except Exception:
            logger.exception("identity_merge_failed canonical=%s email=%s", canonical_user_id, email)
            return False

    def link_identity(
        self,
        canonical_user_id: str,
        *,
        link_email: Optional[str] = None,
        link_telegram: Optional[str] = None,
    ) -> bool:
        """
        Link additional identity sources to an existing canonical user.

        Example: A guest session later authenticates with email.
        """
        try:
            updates: Dict[str, Any] = {}
            if link_email:
                updates["email"] = link_email
                log_identity_link(
                    canonical_user_id=canonical_user_id,
                    link_type="email",
                    link_value=link_email,
                )
            if link_telegram:
                updates["telegram_username"] = link_telegram
                log_identity_link(
                    canonical_user_id=canonical_user_id,
                    link_type="telegram",
                    link_value=link_telegram,
                )

            if updates:
                upsert_profile(user_id=canonical_user_id, updates=updates)
                logger.info("identity_linked canonical=%s updates=%s", canonical_user_id, list(updates.keys()))
                return True

            return False
        except Exception:
            logger.exception("identity_link_failed canonical=%s", canonical_user_id)
            return False

    def get_resolution(self, canonical_user_id: str) -> Optional[IdentityResolution]:
        """Get cached resolution for a user."""
        return self._cache.get(canonical_user_id)


# Module-level singleton
_identity_resolver = IdentityResolver()


def resolve_canonical_user(
    *,
    email: Optional[str] = None,
    telegram_username: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    session_id: Optional[str] = None,
    jotform_submission: Optional[Dict[str, Any]] = None,
    cv_extracted_email: Optional[str] = None,
    is_jwt: bool = False,
) -> IdentityResolution:
    """
    Convenience function to resolve canonical user identity.

    Uses the singleton IdentityResolver instance.

    Args:
        email: User email from JWT, Jotform, or CV
        telegram_username: Telegram handle from Jotform or Telegram
        telegram_chat_id: Numeric Telegram chat ID from webhook
        session_id: Guest session ID for public chat
        jotform_submission: Full Jotform submission payload
        cv_extracted_email: Email extracted from CV parsing
        is_jwt: Explicit flag indicating JWT-authenticated context

    Returns:
        IdentityResolution with canonical user_id and resolution metadata
    """
    return _identity_resolver.resolve(
        email=email,
        telegram_username=telegram_username,
        telegram_chat_id=telegram_chat_id,
        session_id=session_id,
        jotform_submission=jotform_submission,
        cv_extracted_email=cv_extracted_email,
        is_jwt=is_jwt,
    )
