"""Account and token schemas."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from .common import ORMModel

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,60}$")


class RegisterRequest(ORMModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        if not _USERNAME_RE.match(value):
            raise ValueError(
                "username may contain only letters, digits, dot, dash and underscore"
            )
        return value

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        # Length does most of the work; reject the obviously weak rest.
        if value.strip() != value:
            raise ValueError("password must not start or end with whitespace")
        if value.lower() in {"password", "12345678", "qwertyui", "wavelane"}:
            raise ValueError("password is too common")
        return value


class LoginRequest(ORMModel):
    # Either email or username is accepted here.
    login: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    device_name: str | None = Field(default=None, max_length=160)


class RefreshRequest(ORMModel):
    refresh_token: str = Field(min_length=10)


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    username: str
    display_name: str
    avatar_path: str | None = None
    is_admin: bool = False
    created_at: datetime | None = None


class TokenPair(ORMModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class AccessTokenOut(ORMModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class SessionOut(ORMModel):
    id: uuid.UUID
    device_name: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime
    current: bool = False


class PasswordChange(ORMModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ProfileUpdate(ORMModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
