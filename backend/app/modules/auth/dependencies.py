from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status

from app.api.deps import SessionDep
from app.api.errors import api_error
from app.modules.auth.models import UserSession
from app.modules.auth.session import (
    SESSION_COOKIE_NAME,
    get_active_session,
    is_recently_authenticated,
)
from app.modules.users.models import User

SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)]


async def get_optional_session(
    db: SessionDep, session_token: SessionToken = None
) -> UserSession | None:
    if session_token is None:
        return None

    user_session = await get_active_session(db, session_token)
    # Saves the idle refresh, or the deletion of an expired session.
    await db.commit()

    return user_session


OptionalSession = Annotated[UserSession | None, Depends(get_optional_session)]


async def get_current_session(user_session: OptionalSession) -> UserSession:
    if user_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")

    return user_session


CurrentSession = Annotated[UserSession, Depends(get_current_session)]


async def get_current_user(user_session: CurrentSession) -> User:
    return user_session.user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_recently_authenticated_session(
    user_session: CurrentSession,
) -> UserSession:
    """The session, if it proved the person present within RECENT_AUTH_WINDOW:
    what adding or removing a sign-in method requires, so a stolen or
    unattended session alone can't."""

    if not is_recently_authenticated(user_session):
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "reauthentication_required",
            "Confirm it's you to continue.",
        )

    return user_session


RecentlyAuthenticatedSession = Annotated[
    UserSession, Depends(get_recently_authenticated_session)
]
