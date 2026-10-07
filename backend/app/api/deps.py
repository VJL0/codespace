"""Dependencies for what the lifespan creates; tests override these."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx2
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.email import EmailSender
from app.lifespan import get_app_state
from app.modules.auth.providers.registry import OAuthProviders


async def get_engine(request: Request) -> AsyncEngine:
    return get_app_state(request)["engine"]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with get_app_state(request)["session_factory"]() as session:
        yield session


async def get_email_sender(request: Request) -> EmailSender:
    return get_app_state(request)["email_sender"]


async def get_http_client(request: Request) -> httpx2.AsyncClient:
    return get_app_state(request)["http_client"]


async def get_oauth_providers(request: Request) -> OAuthProviders:
    return get_app_state(request)["oauth_providers"]


SessionDep = Annotated[AsyncSession, Depends(get_session)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
HttpClientDep = Annotated[httpx2.AsyncClient, Depends(get_http_client)]
OAuthProvidersDep = Annotated[OAuthProviders, Depends(get_oauth_providers)]
