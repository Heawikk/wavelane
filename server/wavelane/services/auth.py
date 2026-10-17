"""Registration, login and refresh-token rotation."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..models import AuthSession, User
from ..utils import as_aware, now_utc
from .security import (
    AuthError,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User
    session_id: uuid.UUID


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    # --- registration -------------------------------------------------------

    async def register(
        self,
        *,
        email: str,
        username: str,
        password: str,
        display_name: str | None = None,
    ) -> User:
        email = email.strip().lower()
        username = username.strip()

        clash = await self.session.scalar(
            select(User).where(
                or_(
                    func.lower(User.email) == email,
                    func.lower(User.username) == username.lower(),
                )
            )
        )
        if clash is not None:
            field = "email" if clash.email.lower() == email else "username"
            raise ValueError(f"this {field} is already registered")

        # The very first account to exist administers the instance.
        existing_users = await self.session.scalar(select(func.count()).select_from(User))
        user = User(
            email=email,
            username=username,
            display_name=(display_name or username).strip(),
            password_hash=hash_password(password),
            is_admin=existing_users == 0,
        )
        self.session.add(user)
        await self.session.flush()
        logger.info("registered user %s (admin=%s)", username, user.is_admin)
        return user

    # --- login --------------------------------------------------------------

    async def authenticate(self, login: str, password: str) -> User:
        login = login.strip()
        user = await self.session.scalar(
            select(User).where(
                or_(
                    func.lower(User.email) == login.lower(),
                    func.lower(User.username) == login.lower(),
                )
            )
        )
        if user is None:
            # Spend the same time as a real verification would, so response
            # timing does not reveal whether an account exists.
            hash_password(password)
            raise AuthError("invalid credentials")

        if not verify_password(password, user.password_hash):
            raise AuthError("invalid credentials")
        if not user.is_active:
            raise AuthError("account is disabled")

        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        user.last_seen_at = now_utc()
        return user

    # --- token issuing ------------------------------------------------------

    async def issue_tokens(
        self,
        user: User,
        *,
        device_name: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> IssuedTokens:
        raw_refresh, token_hash = generate_refresh_token()
        auth_session = AuthSession(
            user_id=user.id,
            token_hash=token_hash,
            created_at=now_utc(),
            last_used_at=now_utc(),
            expires_at=now_utc() + timedelta(days=self.settings.refresh_token_ttl_days),
            device_name=device_name,
            user_agent=(user_agent or "")[:400] or None,
            ip_address=(ip_address or "")[:64] or None,
        )
        self.session.add(auth_session)
        await self.session.flush()

        access = create_access_token(
            user.id, is_admin=user.is_admin, settings=self.settings
        )
        return IssuedTokens(
            access_token=access.token,
            refresh_token=raw_refresh,
            expires_in=access.expires_in,
            user=user,
            session_id=auth_session.id,
        )

    async def refresh(self, raw_refresh_token: str) -> IssuedTokens:
        """Rotate a refresh token. Reusing a rotated token kills the whole chain."""
        token_hash = hash_refresh_token(raw_refresh_token)
        auth_session = await self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        if auth_session is None:
            raise AuthError("unknown refresh token")

        if auth_session.replaced_by_id is not None:
            # This token was already exchanged. Either it leaked or a client is
            # retrying; revoke every descendant and make the user log in again.
            await self._revoke_chain(auth_session)
            # Commit before raising: this request ends in an error, and the
            # session dependency rolls back on an exception, which would undo
            # the revocation we just performed.
            await self.session.commit()
            logger.warning(
                "refresh token reuse detected for user %s", auth_session.user_id
            )
            raise AuthError("refresh token already used")

        if auth_session.is_revoked:
            raise AuthError("session revoked")

        expires_at = as_aware(auth_session.expires_at)
        if expires_at is not None and expires_at <= now_utc():
            raise AuthError("refresh token expired")

        user = await self.session.get(User, auth_session.user_id)
        if user is None or not user.is_active:
            raise AuthError("account unavailable")

        issued = await self.issue_tokens(
            user,
            device_name=auth_session.device_name,
            user_agent=auth_session.user_agent,
            ip_address=auth_session.ip_address,
        )
        auth_session.replaced_by_id = issued.session_id
        auth_session.revoked_at = now_utc()
        user.last_seen_at = now_utc()
        return issued

    async def _revoke_chain(self, auth_session: AuthSession) -> None:
        """Walk the rotation chain forward and revoke everything in it."""
        seen: set[uuid.UUID] = set()
        current: AuthSession | None = auth_session
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.revoked_at is None:
                current.revoked_at = now_utc()
            next_id = current.replaced_by_id
            current = await self.session.get(AuthSession, next_id) if next_id else None

    async def logout(self, raw_refresh_token: str) -> bool:
        token_hash = hash_refresh_token(raw_refresh_token)
        auth_session = await self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        if auth_session is None:
            return False
        auth_session.revoked_at = auth_session.revoked_at or now_utc()
        return True

    async def logout_all(self, user_id: uuid.UUID) -> int:
        sessions = await self.session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
            )
        )
        count = 0
        for auth_session in sessions:
            auth_session.revoked_at = now_utc()
            count += 1
        return count

    async def list_sessions(self, user_id: uuid.UUID) -> list[AuthSession]:
        rows = await self.session.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .order_by(AuthSession.created_at.desc())
        )
        return list(rows)

    async def revoke_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        auth_session = await self.session.get(AuthSession, session_id)
        if auth_session is None or auth_session.user_id != user_id:
            return False
        auth_session.revoked_at = auth_session.revoked_at or now_utc()
        return True

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise AuthError("current password is incorrect")
        user.password_hash = hash_password(new_password)
        # A password change should log every other device out.
        await self.logout_all(user.id)
