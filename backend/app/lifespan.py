from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict, cast

import httpx2
import resend
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.email import (
    EmailSender,
    Httpx2ResendClient,
    LogEmailSender,
    ResendEmailSender,
)
from app.database import create_database_engine, create_session_factory
from app.modules.auth.providers.registry import (
    OAuthProviders,
    create_oauth_providers,
)


class AppState(TypedDict):
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    oauth_providers: OAuthProviders
    # For outside services (HIBP, Resend), shared so connections are reused.
    http_client: httpx2.AsyncClient
    email_sender: EmailSender


def create_email_sender(http_client: httpx2.AsyncClient) -> EmailSender:
    if not settings.is_production:
        return LogEmailSender()

    resend.api_key = settings.resend_api_key
    resend.default_async_http_client = Httpx2ResendClient(http_client)

    return ResendEmailSender(settings.email_from)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[AppState]:
    engine = create_database_engine()

    async with httpx2.AsyncClient(timeout=10) as http_client:
        try:
            yield {
                "engine": engine,
                "session_factory": create_session_factory(engine),
                "oauth_providers": create_oauth_providers(),
                "http_client": http_client,
                "email_sender": create_email_sender(http_client),
            }
        finally:
            await engine.dispose()


def get_app_state(request: Request) -> AppState:
    return cast(AppState, request.state)
