"""
src/api/routers/settings.py
Thin HTTP layer for user settings.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user_id
from src.schemas.settings import SettingsResponse, SettingsUpdateRequest
from src.services.settings_service import get_settings, update_settings

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def read_settings(user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    return get_settings(user_id=user_id)


@router.put("", response_model=SettingsResponse)
def write_settings(
    body: SettingsUpdateRequest,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return update_settings(data, user_id=user_id)
