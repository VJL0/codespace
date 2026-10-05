"""Fixtures for driving the app over HTTP, in process."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx2
import pytest
from joserfc.jwk import RSAKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_session
from app.main import app
from app.modules.auth.dependencies import get_oauth_provider_registry
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.registry import create_oauth_provider_registry
from tests.support.environment import API_URL, PROVIDER_CREDENTIALS
from tests.support.fake_oauth import FakeOAuthServer, generate_keys


@pytest.fixture(scope="session")
def signing_keys() -> dict[str, RSAKey]:
    # RSA key generation is slow; the keys are public test data, so share them.
    return generate_keys()


@pytest.fixture
def fake_oauth(signing_keys: dict[str, RSAKey]) -> FakeOAuthServer:
    return FakeOAuthServer(keys=signing_keys, credentials=PROVIDER_CREDENTIALS)


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], fake_oauth: FakeOAuthServer
) -> AsyncIterator[httpx2.AsyncClient]:
    """An HTTP client for the app, with its OAuth clients pointed at
    `fake_oauth` and its database sessions on the test's transaction.

    The ASGI transport doesn't run the lifespan; what it would set up is
    overridden here.
    """

    registry = create_oauth_provider_registry()

    for provider in OAuthProvider:
        registry.get(provider).client.client_kwargs["transport"] = fake_oauth.transport

    # A fresh session per request, as in production, all on the test's
    # connection so the request's writes are rolled back with it.
    async def get_test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_oauth_provider_registry] = lambda: registry

    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=API_URL
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
