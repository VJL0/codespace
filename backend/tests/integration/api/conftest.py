"""Fixtures for driving the app over HTTP, in process."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx2
import pytest
from joserfc.jwk import RSAKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import (
    get_email_sender,
    get_http_client,
    get_oauth_providers,
    get_session,
)
from app.main import app
from app.modules.auth.providers.registry import create_oauth_providers
from tests.support.auth_flow import SAME_ORIGIN_HEADERS
from tests.support.email import OutboxEmailSender
from tests.support.environment import APP_URL, PROVIDER_CREDENTIALS
from tests.support.fake_oauth import FakeOAuthServer, generate_keys
from tests.support.fake_pwned import FakePwnedPasswords


@pytest.fixture(scope="session")
def signing_keys() -> dict[str, RSAKey]:
    # RSA key generation is slow; the keys are public test data, so share them.
    return generate_keys()


@pytest.fixture
def fake_oauth(signing_keys: dict[str, RSAKey]) -> FakeOAuthServer:
    return FakeOAuthServer(keys=signing_keys, credentials=PROVIDER_CREDENTIALS)


@pytest.fixture
def outbox() -> OutboxEmailSender:
    return OutboxEmailSender()


@pytest.fixture
def fake_pwned() -> FakePwnedPasswords:
    return FakePwnedPasswords()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
    fake_pwned: FakePwnedPasswords,
) -> AsyncIterator[httpx2.AsyncClient]:
    """An HTTP client for the app, with its OAuth clients pointed at
    `fake_oauth`, its email going to `outbox`, Pwned Passwords answered by
    `fake_pwned`, and its database sessions on the test's transaction. It
    sends what the SPA's own requests do, so it passes the CSRF check.

    The ASGI transport doesn't run the lifespan; what it would set up is
    overridden here.
    """

    providers = create_oauth_providers()

    for adapter in providers.values():
        adapter.client.client_kwargs["transport"] = fake_oauth.transport

    # A fresh session per request, as in production, all on the test's
    # connection so the request's writes are rolled back with it.
    async def get_test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_oauth_providers] = lambda: providers
    app.dependency_overrides[get_email_sender] = lambda: outbox

    outside = httpx2.AsyncClient(transport=fake_pwned.transport)
    app.dependency_overrides[get_http_client] = lambda: outside

    try:
        async with (
            outside,
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url=APP_URL,
                headers=SAME_ORIGIN_HEADERS,
            ) as client,
        ):
            yield client
    finally:
        app.dependency_overrides.clear()
