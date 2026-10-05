"""The API as Playwright's browser tests run it: `uv run python -m tests.e2e.server`.

The real app on a throwaway PostgreSQL container, with its OAuth clients on
the in-process fake providers. The browser can't reach those, so the
frontend tests reroute the providers' authorization pages to a test-only
route here, which approves the request as the fake would and redirects to
the app's callback. That route is mounted only by this script, never by
`app/`.

The ports differ from the dev servers' (Vite :5173, uvicorn :8000), so a
run never lands on, or is blocked by, an app you have open. They must match
frontend/playwright.config.ts.
"""

from __future__ import annotations

import json
import os

from tests.support.environment import app_environment

PORT = 8001
APP_URL = "http://localhost:5174"

os.environ.update(
    {
        **app_environment(),
        "APP_URL": APP_URL,
        # localhost: requests proxied by Vite; 127.0.0.1: Playwright's
        # readiness probe.
        "ALLOWED_HOSTS": '["localhost", "127.0.0.1"]',
    }
)

import uvicorn
from alembic import command
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from testcontainers.community.postgres import PostgresContainer

from app.core.config import settings
from app.main import app
from app.modules.auth.dependencies import get_oauth_provider_registry
from app.modules.auth.models import OAuthProvider
from app.modules.auth.providers.registry import (
    create_oauth_provider_registry,
)
from tests.support.database import alembic_config
from tests.support.environment import PROVIDER_CREDENTIALS
from tests.support.fake_oauth import FakeOAuthServer, generate_keys

fake_oauth = FakeOAuthServer(keys=generate_keys(), credentials=PROVIDER_CREDENTIALS)

e2e_router = APIRouter()


@e2e_router.get("/oauth/authorize")
async def approve_authorization(url: str, scenario: str) -> RedirectResponse:
    """Answer the provider authorization request `url` as `scenario` says.

    `scenario` is JSON of `FakeOAuthServer.authorize` keyword arguments: the
    claims or GitHub profile to sign in as, or an `error` to deny with.
    """

    return RedirectResponse(fake_oauth.authorize(url, **json.loads(scenario)))


def main() -> None:
    registry = create_oauth_provider_registry()

    for provider in OAuthProvider:
        registry.get(provider).client.client_kwargs["transport"] = fake_oauth.transport

    app.dependency_overrides[get_oauth_provider_registry] = lambda: registry
    app.include_router(e2e_router, prefix="/api/__e2e__")

    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as postgres:
        settings.database_url = postgres.get_connection_url()
        command.upgrade(alembic_config(), "head")

        uvicorn.run(app, host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
