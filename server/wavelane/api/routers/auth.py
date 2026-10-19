"""Authentication endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status

from ...schemas.auth import (
    AccessTokenOut,
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    RefreshRequest,
    RegisterRequest,
    SessionOut,
    TokenPair,
    UserOut,
)
from ...schemas.common import Message
from ...services.auth import AuthService
from ...services.ratelimit import RateLimiter, get_rate_limiter
from ...services.security import AuthError
from ..deps import AppSettings, ClientIp, CurrentUser, DbSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Failed sign-ins: per address and account together (so a stranger cannot lock the
# owner out of their own account), per address overall, and per account overall
# (a guess spread over many addresses). Each is (limit, window in seconds).
LOGIN_PAIR_FAILURES = (6, 15 * 60)
LOGIN_ADDRESS_FAILURES = (30, 15 * 60)
LOGIN_ACCOUNT_FAILURES = (60, 60 * 60)
REGISTRATIONS_PER_ADDRESS = (5, 60 * 60)
REFRESHES_PER_ADDRESS = (120, 60)
PASSWORD_FAILURES = (5, 15 * 60)


def _too_many(seconds: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="too many attempts; try again later",
        headers={"Retry-After": str(seconds)},
    )


def _wait_for(limiter: RateLimiter, checks: list[tuple[str, tuple[int, int]]]) -> None:
    """Refuse with 429 if any of the (key, (limit, window)) pairs is used up."""
    wait = max(
        (limiter.retry_after(key, limit, window) for key, (limit, window) in checks),
        default=0,
    )
    if wait:
        raise _too_many(wait)


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and sign in",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    ip: ClientIp,
) -> TokenPair:
    if not settings.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="registration is closed on this server",
        )

    limiter = get_rate_limiter()
    _wait_for(limiter, [(f"register:{ip}", REGISTRATIONS_PER_ADDRESS)])
    # Every attempt counts, successful or not: the point is to stop account spam.
    limiter.add(f"register:{ip}")

    service = AuthService(db, settings)
    try:
        user = await service.register(
            email=payload.email,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    issued = await service.issue_tokens(
        user,
        device_name=None,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )
    return TokenPair(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenPair, summary="Sign in with email or username")
async def login(
    payload: LoginRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    ip: ClientIp,
) -> TokenPair:
    account = payload.login.strip().lower()
    limiter = get_rate_limiter()
    pair, address, whole = f"login:{ip}|{account}", f"login:{ip}", f"login-account:{account}"
    _wait_for(
        limiter,
        [
            (pair, LOGIN_PAIR_FAILURES),
            (address, LOGIN_ADDRESS_FAILURES),
            (whole, LOGIN_ACCOUNT_FAILURES),
        ],
    )

    service = AuthService(db, settings)
    try:
        user = await service.authenticate(payload.login, payload.password)
    except AuthError as exc:
        for key in (pair, address, whole):
            limiter.add(key)
        logger.warning("failed sign-in for %r from %s", account[:60], ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    limiter.clear(pair)
    issued = await service.issue_tokens(
        user,
        device_name=payload.device_name,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )
    return TokenPair(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        user=UserOut.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=AccessTokenOut,
    summary="Exchange a refresh token for a new pair",
)
async def refresh(
    payload: RefreshRequest, db: DbSession, settings: AppSettings, ip: ClientIp
) -> AccessTokenOut:
    limiter = get_rate_limiter()
    _wait_for(limiter, [(f"refresh:{ip}", REFRESHES_PER_ADDRESS)])
    limiter.add(f"refresh:{ip}")

    service = AuthService(db, settings)
    try:
        issued = await service.refresh(payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AccessTokenOut(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
    )


@router.post("/logout", response_model=Message, summary="Revoke one refresh token")
async def logout(
    payload: RefreshRequest, db: DbSession, settings: AppSettings
) -> Message:
    service = AuthService(db, settings)
    revoked = await service.logout(payload.refresh_token)
    return Message(detail="signed out" if revoked else "token was already invalid")


@router.post(
    "/logout-all", response_model=Message, summary="Revoke every session of this account"
)
async def logout_all(user: CurrentUser, db: DbSession, settings: AppSettings) -> Message:
    count = await AuthService(db, settings).logout_all(user.id)
    return Message(detail=f"revoked {count} session(s)")


@router.get("/me", response_model=UserOut, summary="The signed-in account")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut, summary="Update the signed-in account")
async def update_me(payload: ProfileUpdate, user: CurrentUser, db: DbSession) -> UserOut:
    if payload.display_name:
        user.display_name = payload.display_name.strip()
    await db.flush()
    return UserOut.model_validate(user)


@router.post("/password", response_model=Message, summary="Change the password")
async def change_password(
    payload: PasswordChange, user: CurrentUser, db: DbSession, settings: AppSettings
) -> Message:
    limiter = get_rate_limiter()
    key = f"password:{user.id}"
    _wait_for(limiter, [(key, PASSWORD_FAILURES)])

    service = AuthService(db, settings)
    try:
        await service.change_password(user, payload.current_password, payload.new_password)
    except AuthError as exc:
        # A stolen access token must not be a free way to test the current password.
        limiter.add(key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return Message(detail="password changed; other devices were signed out")


@router.get("/sessions", response_model=list[SessionOut], summary="Active devices")
async def list_sessions(
    user: CurrentUser, db: DbSession, settings: AppSettings
) -> list[SessionOut]:
    sessions = await AuthService(db, settings).list_sessions(user.id)
    return [SessionOut.model_validate(item) for item in sessions]


@router.delete(
    "/sessions/{session_id}", response_model=Message, summary="Sign a device out"
)
async def revoke_session(
    session_id: uuid.UUID, user: CurrentUser, db: DbSession, settings: AppSettings
) -> Message:
    revoked = await AuthService(db, settings).revoke_session(user.id, session_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return Message(detail="session revoked")
