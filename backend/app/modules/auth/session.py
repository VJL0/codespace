from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.auth.models import UserSession
from app.modules.auth.repository import UserSessionRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

if TYPE_CHECKING:
    from fastapi import Response
    from sqlalchemy.ext.asyncio import AsyncSession

TOKEN_BYTES = 32
SESSION_COOKIE_NAME = "__Host-Http-session"
SESSION_ABSOLUTE_TIMEOUT = timedelta(days=14)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionService:
    def __init__(self, sessions: UserSessionRepository, users: UserRepository) -> None:
        self._sessions = sessions
        self._users = users

    def create_session(self, *, user: User) -> str:
        token = secrets.token_urlsafe(TOKEN_BYTES)

        # By relationship rather than user.id: a user created in this same
        # transaction has no id until the flush.
        self._sessions.add(
            UserSession(
                user=user,
                token_hash=_hash_token(token),
                expires_at=datetime.now(UTC) + SESSION_ABSOLUTE_TIMEOUT,
            )
        )

        return token

    async def get_user_for_session(self, token: str) -> User | None:
        """Return the active user a session token belongs to, or None."""

        user_session = await self._sessions.get_by_token_hash(_hash_token(token))

        if user_session is None:
            return None

        now = datetime.now(UTC)

        is_expired = now >= user_session.expires_at
        is_idle = now - user_session.last_seen_at >= timedelta(minutes=30)

        if is_expired or is_idle:
            await self._sessions.delete(user_session)
            return None

        # Refresh the idle deadline at most once a minute, so authenticated
        # requests don't each cost a write.
        if now - user_session.last_seen_at > timedelta(minutes=1):
            user_session.last_seen_at = now

        user = await self._users.get(user_session.user_id)

        if user is None or not user.is_active:
            return None

        return user

    async def revoke_session(self, token: str) -> None:
        await self._sessions.delete_by_token_hash(_hash_token(token))

    async def revoke_all_sessions(self, user: User) -> None:
        await self._sessions.delete_for_user(user.id)


async def finish_sign_in(
    db: AsyncSession,
    session_service: SessionService,
    response: Response,
    *,
    user: User,
    previous_token: str | None,
) -> None:
    """Start a fresh session for `user` and set its cookie on `response`.

    A session the browser already had is revoked rather than reused, so a
    token planted before sign-in (session fixation) never becomes signed in.
    """

    if previous_token is not None:
        await session_service.revoke_session(previous_token)

    token = session_service.create_session(user=user)
    await db.commit()

    set_session_cookie(response, token=token)


def set_session_cookie(response: Response, *, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=int(SESSION_ABSOLUTE_TIMEOUT.total_seconds()),
        path="/",
        samesite="lax",
        secure=True,
        httponly=True,
    )


def delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=True,
        httponly=True,
    )
