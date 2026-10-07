"""GET /api/auth/me, POST /api/auth/logout and /logout-all: using and ending
sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx2
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import UserSession
from tests.support.auth_flow import (
    GOOGLE_CLAIMS,
    SESSION_COOKIE,
    approval,
    set_session_token,
    sign_in,
)
from tests.support.database import count_rows
from tests.support.fake_oauth import FakeOAuthServer


async def signed_in(client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer) -> str:
    """Sign in with Google and return the session token."""

    await sign_in(client, fake_oauth, "google", claims=GOOGLE_CLAIMS)

    return client.cookies[SESSION_COOKIE]


async def test_me_requires_a_session(client: httpx2.AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_activity_refresh_is_committed(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    # The request's own session closes after the response; without a commit
    # its refresh of last_seen_at would be rolled back with it.
    await signed_in(client, fake_oauth)
    stale = datetime.now(UTC) - timedelta(minutes=5)
    await db.execute(update(UserSession).values(last_seen_at=stale))

    assert (await client.get("/api/auth/me")).status_code == 200

    last_seen_at = await db.scalar(select(UserSession.last_seen_at))
    assert last_seen_at is not None
    assert last_seen_at > stale


async def test_logout_revokes_the_session(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    token = await signed_in(client, fake_oauth)

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert await count_rows(db, UserSession) == 0

    # The old token is dead server-side too, not just forgotten by the browser.
    set_session_token(client, token)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_without_a_session_succeeds(client: httpx2.AsyncClient) -> None:
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_logout_all_requires_a_session(client: httpx2.AsyncClient) -> None:
    assert (await client.post("/api/auth/logout-all")).status_code == 401


async def test_logout_all_revokes_every_session_of_the_user(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    # Two browsers: sign in, forget the cookie, sign in again.
    other_browser = await signed_in(client, fake_oauth)
    client.cookies.clear()
    this_browser = await signed_in(client, fake_oauth)
    assert await count_rows(db, UserSession) == 2

    response = await client.post("/api/auth/logout-all")

    assert response.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert await count_rows(db, UserSession) == 0

    for token in (other_browser, this_browser):
        set_session_token(client, token)
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_all_leaves_other_users_signed_in(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(client, fake_oauth, "github", **approval("github"))
    someone_else = client.cookies[SESSION_COOKIE]
    client.cookies.clear()
    await signed_in(client, fake_oauth)

    await client.post("/api/auth/logout-all")

    set_session_token(client, someone_else)
    assert (await client.get("/api/auth/me")).status_code == 200
