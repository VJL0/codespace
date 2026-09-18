from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status

from app.api.deps import DbSession
from app.core.config import settings
from app.modules.auth.session import get_user_id_for_session
from app.modules.users.models import User

AuthSessionToken = Annotated[
    str | None,
    Cookie(alias=settings.auth_session_cookie_name),
]


async def get_current_user(
    db: DbSession,
    session_token: AuthSessionToken = None,
) -> User:
    if session_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")

    user_id = await get_user_id_for_session(db, session_token)

    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid.")

    user = await db.get(User, user_id)

    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found.")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
