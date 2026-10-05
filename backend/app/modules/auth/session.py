from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.auth.models import UserSession
from app.modules.auth.repository import UserSessionRepository
from app.modules.auth.tokens import hash_secret, new_secret
from app.modules.users.models import User

if TYPE_CHECKING:
    from fastapi import Response
    from sqlalchemy.ext.asyncio import AsyncSession

SESSION_COOKIE_NAME = "__Host-Http-session"
SESSION_ABSOLUTE_TIMEOUT = timedelta(days=14)
# How long after a fresh authentication sensitive changes stay allowed.
RECENT_AUTH_WINDOW = timedelta(minutes=10)


def is_recently_authenticated(user_session: UserSession) -> bool:
    """Whether the session's last fresh authentication is recent enough for
    a sensitive change (linking, unlinking, credential changes)."""

    authenticated_at = user_session.authenticated_at

    return (
        authenticated_at is not None
        and datetime.now(UTC) - authenticated_at <= RECENT_AUTH_WINDOW
    )


class SessionService:
    def __init__(self, sessions: UserSessionRepository) -> None:
        self._sessions = sessions

    def create_session(self, *, user: User, fresh: bool) -> str:
        """Start a session; `fresh` when the sign-in proved the person is
        present (a password, an email link), not just a provider's SSO."""

        token = new_secret()
        now = datetime.now(UTC)

        # By relationship rather than user.id: a user created in this same
        # transaction has no id until the flush.
        self._sessions.add(
            UserSession(
                user=user,
                token_hash=hash_secret(token),
                authenticated_at=now if fresh else None,
                expires_at=now + SESSION_ABSOLUTE_TIMEOUT,
            )
        )

        return token

    def reauthenticate(self, user_session: UserSession) -> str:
        """Record a fresh authentication on this session and renew its token.

        The same session, so its age and expiry stand; a new token, as after
        any change in what a session may do.
        """

        token = new_secret()
        user_session.token_hash = hash_secret(token)
        user_session.authenticated_at = datetime.now(UTC)

        return token

    async def get_active_session(self, token: str) -> UserSession | None:
        """Return the live session for a token, with its active user loaded,
        or None."""

        user_session = await self._sessions.get_by_token_hash(hash_secret(token))

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

        if not user_session.user.is_active:
            return None

        return user_session

    async def revoke_session(self, token: str) -> None:
        await self._sessions.delete_by_token_hash(hash_secret(token))

    async def revoke_all_sessions(self, user_id: uuid.UUID) -> None:
        await self._sessions.delete_for_user(user_id)

    async def revoke_other_sessions(self, user_session: UserSession) -> None:
        """Sign the user out everywhere but this session."""

        await self._sessions.delete_for_user(user_session.user_id, keep=user_session.id)


async def finish_sign_in(
    db: AsyncSession,
    session_service: SessionService,
    response: Response,
    *,
    user: User,
    previous_token: str | None,
    fresh: bool,
) -> None:
    """Start a fresh session for `user` and set its cookie on `response`.

    A session the browser already had is revoked rather than reused, so a
    token planted before sign-in (session fixation) never becomes signed in.
    """

    if previous_token is not None:
        await session_service.revoke_session(previous_token)

    token = session_service.create_session(user=user, fresh=fresh)
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
