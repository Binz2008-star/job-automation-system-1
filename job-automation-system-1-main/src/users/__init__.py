"""src/users/
Multi-user daily scheduler and pipeline orchestration.

This module is the future home for per-user job pipeline execution.
Phase 1 contains only the scheduler skeleton.
"""
from __future__ import annotations

from src.users.scheduler import UserScheduler

__all__ = ["UserScheduler"]
