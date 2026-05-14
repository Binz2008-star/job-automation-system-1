from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=256, pattern=_EMAIL_RE)
    password: str = Field(..., min_length=1, max_length=128)
    public_user_id_to_merge: str | None = Field(
        None,
        description="Optional public guest user ID to merge profile data from after login",
    )


class LoginResponse(BaseModel):
    message: str
    email: str


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=256)
    password: str = Field(..., min_length=8, max_length=128,
                          description="Minimum 8 characters")
    role: Literal["admin", "user"] = Field("user", description="User role")
    public_user_id_to_merge: str | None = Field(
        None,
        description="Optional public guest user ID to merge profile data from after signup",
    )


class RegisterResponse(BaseModel):
    email: str
    role: str
    created: bool


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=256, pattern=_EMAIL_RE)


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token:        str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8,  max_length=128)


class ResetPasswordResponse(BaseModel):
    message: str
