from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.api.deps import SessionDep
from app.lifespan import get_app_state
from app.modules.auth.providers.registry import OAuthProviderRegistry
from app.modules.auth.repository import OAuthAccountRepository, UserSessionRepository
from app.modules.auth.service import AuthService
from app.modules.auth.session import SESSION_COOKIE_NAME, SessionService
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

AuthSessionToken = Annotated[
    str | None,
    Cookie(alias=SESSION_COOKIE_NAME),
]


async def get_auth_service(db: SessionDep) -> AuthService:
    return AuthService(OAuthAccountRepository(db), UserRepository(db))


async def get_session_service(db: SessionDep) -> SessionService:
    return SessionService(UserSessionRepository(db), UserRepository(db))


async def get_oauth_provider_registry(request: Request) -> OAuthProviderRegistry:
    return get_app_state(request)["oauth_providers"]


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
OAuthProviderRegistryDep = Annotated[
    OAuthProviderRegistry, Depends(get_oauth_provider_registry)
]


async def get_optional_user(
    db: SessionDep,
    session_service: SessionServiceDep,
    session_token: AuthSessionToken = None,
) -> User | None:
    if session_token is None:
        return None

    user = await session_service.get_user_for_session(session_token)

    await db.commit()

    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
