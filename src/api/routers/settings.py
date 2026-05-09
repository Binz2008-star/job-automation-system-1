"""
src/api/routers/settings.py
Thin HTTP layer for user settings.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user
from src.schemas.settings import SettingsResponse, SettingsUpdateRequest
from src.services.settings_service import get_settings, update_settings

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def read_settings(_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return get_settings()


@router.put("", response_model=SettingsResponse)
def write_settings(
    body: SettingsUpdateRequest,
    _user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return update_settings(data)
