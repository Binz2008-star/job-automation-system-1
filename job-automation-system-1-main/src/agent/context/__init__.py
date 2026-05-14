"""src/agent/context

Profile context resolution and hydration for Rico agent.

Loads user profile from DB, hydrates from CV/Jotform/chat/actions,
computes missing fields, and prevents repeated questions.
"""
from __future__ import annotations

from src.agent.context.resolver import ProfileContextResolver, resolve_profile_context

__all__ = ["ProfileContextResolver", "resolve_profile_context"]
