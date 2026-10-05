from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict, cast

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.database import create_database_engine, create_session_factory
from app.modules.auth.providers.registry import (
    OAuthProviderRegistry,
    create_oauth_provider_registry,
)


class AppState(TypedDict):
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    oauth_providers: OAuthProviderRegistry


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[AppState]:
    engine = create_database_engine()

    try:
        yield {
            "engine": engine,
            "session_factory": create_session_factory(engine),
            "oauth_providers": create_oauth_provider_registry(),
        }
    finally:
        await engine.dispose()


def get_app_state(request: Request) -> AppState:
    return cast(AppState, request.state)
