from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    message: str
    email: str
