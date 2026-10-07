from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from app.modules.auth.models import UserSession
from app.modules.auth.tokens import hash_secret, new_secret

if TYPE_CHECKING:
    from fastapi import Response
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.users.models import User

SESSION_COOKIE_NAME = "__Host-Http-session"
SESSION_ABSOLUTE_TIMEOUT = timedelta(days=14)
SESSION_IDLE_TIMEOUT = timedelta(minutes=30)
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


async def get_active_session(db: AsyncSession, token: str) -> UserSession | None:
    """The live session for a token, with its active user loaded, or None.
    An expired or idle session is deleted."""

    user_session = await db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(UserSession.token_hash == hash_secret(token))
    )

    if user_session is None:
        return None

    now = datetime.now(UTC)

    if (
        now >= user_session.expires_at
        or now - user_session.last_seen_at >= SESSION_IDLE_TIMEOUT
    ):
        await db.delete(user_session)
        return None

    # Refresh the idle deadline at most once a minute, so authenticated
    # requests don't each cost a write.
    if now - user_session.last_seen_at > timedelta(minutes=1):
        user_session.last_seen_at = now

    return user_session if user_session.user.is_active else None


async def start_session(
    db: AsyncSession,
    response: Response,
    *,
    user: User,
    fresh: bool,
    previous_token: str | None,
) -> None:
    """Sign `user` in: commit a new session and set its cookie on `response`.

    `fresh` when the sign-in proved the person is present (a password, an
    email link), not just a provider's SSO. A session the browser already had
    is revoked rather than reused, so a token planted before sign-in (session
    fixation) never becomes signed in.
    """

    if previous_token is not None:
        await revoke_session(db, previous_token)

    token = new_secret()
    now = datetime.now(UTC)

    # By relationship rather than user.id: a user created in this same
    # transaction has no id until the flush.
    db.add(
        UserSession(
            user=user,
            token_hash=hash_secret(token),
            authenticated_at=now if fresh else None,
            expires_at=now + SESSION_ABSOLUTE_TIMEOUT,
        )
    )
    await db.commit()

    set_session_cookie(response, token)


async def renew_session(
    db: AsyncSession, response: Response, user_session: UserSession
) -> None:
    """Record a fresh authentication on this session, commit, and give it a
    new token.

    The same session, so its age and expiry stand; a new token, as after any
    change in what a session may do.
    """

    token = new_secret()
    user_session.token_hash = hash_secret(token)
    user_session.authenticated_at = datetime.now(UTC)
    await db.commit()

    set_session_cookie(response, token)


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(
        delete(UserSession).where(UserSession.token_hash == hash_secret(token))
    )


async def revoke_sessions(
    db: AsyncSession, user_id: uuid.UUID, *, keep: uuid.UUID | None = None
) -> None:
    """Delete the user's sessions, all of them or all but `keep`."""

    statement = delete(UserSession).where(UserSession.user_id == user_id)

    if keep is not None:
        statement = statement.where(UserSession.id != keep)

    await db.execute(statement)


def set_session_cookie(response: Response, token: str) -> None:
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
