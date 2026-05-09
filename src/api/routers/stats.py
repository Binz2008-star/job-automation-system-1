"""
src/api/routers/stats.py
Aggregated statistics — delegates to the applications repository.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user
from src.repositories.applications_repo import get_stats

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("")
def get_stats_route(_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return get_stats()
