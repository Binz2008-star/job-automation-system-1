"""src/agent/identity

Canonical identity resolution for Rico agent.

Resolves user identity from multiple sources into a single canonical user_id:
- Guest public sessions (public:*)
- Authenticated JWT users (email)
- Jotform submissions (email or telegram_username)
- Telegram users (chat_id)
- CV-extracted identity (email from parsed CV)

All identity sources merge into one canonical user record.
"""
from __future__ import annotations

from src.agent.identity.resolver import IdentityResolver, resolve_canonical_user

__all__ = ["IdentityResolver", "resolve_canonical_user"]
