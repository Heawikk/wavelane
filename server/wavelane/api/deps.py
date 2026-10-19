"""FastAPI dependencies: authentication, pagination, services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_db
from ..models import User
from ..schemas.common import Pagination
from ..services.security import AuthError, decode_token, token_user_id
from ..services.storage import Storage, get_storage

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
FileStorage = Annotated[Storage, Depends(get_storage)]

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=_UNAUTHORIZED_HEADERS,
    )


async def get_current_user(
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("not authenticated")

    try:
        payload = decode_token(
            credentials.credentials, expected_type="access", settings=settings
        )
        user_id = token_user_id(payload)
    except AuthError as exc:
        raise _unauthorized(str(exc)) from exc

    user = await db.get(User, user_id)
    if user is None:
        raise _unauthorized("account no longer exists")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="account is disabled"
        )
    return user


async def get_optional_user(
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User | None:
    """For endpoints that personalise when signed in but work without it."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_token(
            credentials.credentials, expected_type="access", settings=settings
        )
        user = await db.get(User, token_user_id(payload))
    except AuthError:
        return None
    return user if user is not None and user.is_active else None


async def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="administrator rights required"
        )
    return user


def pagination(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


def client_ip(request: Request) -> str | None:
    """The address the request really came from.

    X-Forwarded-For is deliberately not read here: any caller can write it, and
    this address keys the rate limits. Behind a reverse proxy, uvicorn replaces
    the peer address with the forwarded one, but only for proxies listed in
    --forwarded-allow-ips (127.0.0.1 by default), so what arrives here can be trusted.
    """
    return request.client.host if request.client else None


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
AdminUser = Annotated[User, Depends(get_current_admin)]
PageParams = Annotated[Pagination, Depends(pagination)]
ClientIp = Annotated[str | None, Depends(client_ip)]
