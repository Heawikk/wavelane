"""Password hashing, JWT issuing/verification and refresh-token handling."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from ..config import Settings, get_settings
from ..utils import now_utc

TokenType = Literal["access", "stream"]

# Interactive-login profile: ~64 MiB, 3 passes. Tuned so a login costs tens of
# milliseconds on a server CPU while staying expensive to brute-force.
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)


class AuthError(Exception):
    """Raised for any credential or token problem; the API maps it to 401."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


# Hashing is deliberately slow (about 64 MiB and a few tens of milliseconds), so
# it must not run on the event loop, where one login attempt would stop every
# stream; and only a couple may run at once, so a flood of attempts queues
# instead of eating all the memory. The executor does not belong to any loop.
_hash_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="argon2")


async def hash_password_async(password: str) -> str:
    return await asyncio.get_running_loop().run_in_executor(_hash_pool, hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    return await asyncio.get_running_loop().run_in_executor(
        _hash_pool, verify_password, password, password_hash
    )


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than the current profile."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@dataclass(slots=True)
class AccessToken:
    token: str
    expires_at: datetime
    expires_in: int


def create_access_token(
    user_id: uuid.UUID,
    *,
    is_admin: bool = False,
    settings: Settings | None = None,
    extra: dict[str, Any] | None = None,
) -> AccessToken:
    settings = settings or get_settings()
    issued = now_utc()
    expires = issued + timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": "access",
        "adm": is_admin,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_urlsafe(8),
    }
    if extra:
        payload |= extra
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return AccessToken(
        token=token,
        expires_at=expires,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


def create_stream_token(
    user_id: uuid.UUID, track_id: uuid.UUID, settings: Settings | None = None
) -> str:
    """Short-lived token so an <audio> element can fetch a stream without headers."""
    settings = settings or get_settings()
    issued = now_utc()
    payload = {
        "sub": str(user_id),
        "typ": "stream",
        "trk": str(track_id),
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=settings.stream_token_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(
    token: str, *, expected_type: TokenType = "access", settings: Settings | None = None
) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("invalid token") from exc

    if payload.get("typ") != expected_type:
        raise AuthError("wrong token type")
    return payload


def token_user_id(payload: dict[str, Any]) -> uuid.UUID:
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthError("malformed subject") from exc


# --- refresh tokens --------------------------------------------------------
# The raw token goes to the client once and is never stored; only its SHA-256
# lives in the database, so a dump of auth_sessions is not a set of credentials.


def generate_refresh_token() -> tuple[str, str]:
    """Return (raw_token, token_hash)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
