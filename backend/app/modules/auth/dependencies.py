from __future__ import annotations

from typing import Annotated

import httpx2
from fastapi import Cookie, Depends, HTTPException, Request, status

from app.api.deps import SessionDep
from app.core.email import EmailSender
from app.lifespan import get_app_state
from app.modules.auth.models import UserSession
from app.modules.auth.password_service import PasswordService
from app.modules.auth.providers.registry import OAuthProviderRegistry
from app.modules.auth.rate_limit import RateLimiter
from app.modules.auth.repository import (
    OAuthAccountRepository,
    PasswordCredentialRepository,
    UserSessionRepository,
)
from app.modules.auth.service import AuthService
from app.modules.auth.session import (
    SESSION_COOKIE_NAME,
    SessionService,
    is_recently_authenticated,
)
from app.modules.auth.tokens import EmailTokenRepository
from app.modules.users.models import User
from app.modules.users.repository import UserEmailRepository, UserRepository

AuthSessionToken = Annotated[
    str | None,
    Cookie(alias=SESSION_COOKIE_NAME),
]


async def get_auth_service(db: SessionDep) -> AuthService:
    return AuthService(
        OAuthAccountRepository(db),
        UserRepository(db),
        UserEmailRepository(db),
        PasswordCredentialRepository(db),
    )


async def get_password_service(db: SessionDep) -> PasswordService:
    return PasswordService(
        UserRepository(db), UserEmailRepository(db), PasswordCredentialRepository(db)
    )


async def get_email_tokens(db: SessionDep) -> EmailTokenRepository:
    return EmailTokenRepository(db)


async def get_rate_limiter(db: SessionDep) -> RateLimiter:
    return RateLimiter(db)


async def get_email_sender(request: Request) -> EmailSender:
    return get_app_state(request)["email_sender"]


async def get_http_client(request: Request) -> httpx2.AsyncClient:
    return get_app_state(request)["http_client"]


async def get_session_service(db: SessionDep) -> SessionService:
    return SessionService(UserSessionRepository(db))


async def get_oauth_provider_registry(request: Request) -> OAuthProviderRegistry:
    return get_app_state(request)["oauth_providers"]


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
PasswordServiceDep = Annotated[PasswordService, Depends(get_password_service)]
EmailTokensDep = Annotated[EmailTokenRepository, Depends(get_email_tokens)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
HttpClientDep = Annotated[httpx2.AsyncClient, Depends(get_http_client)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
OAuthProviderRegistryDep = Annotated[
    OAuthProviderRegistry, Depends(get_oauth_provider_registry)
]


async def get_optional_session(
    db: SessionDep,
    session_service: SessionServiceDep,
    session_token: AuthSessionToken = None,
) -> UserSession | None:
    if session_token is None:
        return None

    user_session = await session_service.get_active_session(session_token)

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
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "code": "reauthentication_required",
                "message": "Confirm it's you to continue.",
            },
        )

    return user_session


RecentlyAuthenticatedSession = Annotated[
    UserSession, Depends(get_recently_authenticated_session)
]
