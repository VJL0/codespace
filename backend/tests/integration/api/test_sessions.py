"""Using and ending sessions: /me, /logout and /logout-all, and the limits
every signed-in request enforces."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import UserSession
from app.modules.users.models import User
from tests.support.auth_flow import SESSION_COOKIE, approval, set_session_token, sign_in
from tests.support.database import count_rows
from tests.support.fake_oauth import FakeOAuthServer


async def signed_in(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, provider: str = "google"
) -> str:
    """Sign in and return the session token."""

    await sign_in(client, fake_oauth, provider, **approval(provider))

    return client.cookies[SESSION_COOKIE]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/auth/me"),
        ("GET", "/api/auth/methods"),
        ("POST", "/api/auth/logout-all"),
        ("POST", "/api/auth/github/link"),
        ("POST", "/api/auth/reauthenticate/email"),
        ("POST", "/api/auth/password/setup"),
        ("DELETE", "/api/auth/password"),
        ("DELETE", "/api/auth/identities/github"),
    ],
)
async def test_signed_in_endpoints_need_a_session(
    client: httpx2.AsyncClient, method: str, path: str
) -> None:
    assert (await client.request(method, path)).status_code == 401


@pytest.mark.parametrize(
    "times",
    [
        pytest.param({"last_seen_at": func.now() - timedelta(minutes=30)}, id="idle"),
        pytest.param(
            {
                "created_at": func.now() - timedelta(days=15),
                "expires_at": func.now() - timedelta(seconds=1),
            },
            id="expired",
        ),
    ],
)
async def test_an_idle_or_expired_session_is_ended(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    times: dict[str, Any],
) -> None:
    await signed_in(client, fake_oauth)
    await db.execute(update(UserSession).values(**times))

    assert (await client.get("/api/auth/me")).status_code == 401
    assert await count_rows(db, UserSession) == 0


async def test_a_deactivated_user_is_signed_out(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in(client, fake_oauth)
    await db.execute(update(User).values(is_active=False))

    assert (await client.get("/api/auth/me")).status_code == 401


async def test_activity_refreshes_the_idle_deadline(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    # Committed by the request: its own database session closes after the
    # response, and an uncommitted refresh would be rolled back with it.
    await signed_in(client, fake_oauth)
    stale = datetime.now(UTC) - timedelta(minutes=5)
    await db.execute(update(UserSession).values(last_seen_at=stale))

    assert (await client.get("/api/auth/me")).status_code == 200

    last_seen_at = await db.scalar(select(UserSession.last_seen_at))
    assert last_seen_at is not None
    assert last_seen_at > stale


async def test_logout_ends_the_session(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    token = await signed_in(client, fake_oauth)

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    # Ended server-side too, not just forgotten by the browser.
    set_session_token(client, token)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_without_a_session_succeeds(client: httpx2.AsyncClient) -> None:
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_logout_all_ends_every_session_of_the_user_only(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    someone_else = await signed_in(client, fake_oauth, "github")
    client.cookies.clear()
    other_browser = await signed_in(client, fake_oauth)
    client.cookies.clear()
    await signed_in(client, fake_oauth)

    response = await client.post("/api/auth/logout-all")

    assert response.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    set_session_token(client, other_browser)
    assert (await client.get("/api/auth/me")).status_code == 401
    set_session_token(client, someone_else)
    assert (await client.get("/api/auth/me")).status_code == 200
