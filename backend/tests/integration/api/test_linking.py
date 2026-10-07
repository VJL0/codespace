"""Linking and unlinking provider accounts: /api/auth/{provider}/link,
/identities/{provider} and /methods."""

from __future__ import annotations

from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OAuthAccount, OAuthProvider, UserSession
from app.modules.users.models import UserEmail
from tests.support.auth_flow import (
    GITHUB_EMAILS,
    GITHUB_USER,
    MICROSOFT_CLAIMS,
    approval,
    error_code,
    frontend_redirect,
    link,
    set_recently_authenticated,
    sign_in,
    sign_in_methods,
    start_link,
)
from tests.support.database import count_rows
from tests.support.fake_oauth import FakeOAuthServer


async def signed_in_recently(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    """Signed in with Google, and as if just reauthenticated."""

    await sign_in(client, fake_oauth, "google", **approval("google"))
    await set_recently_authenticated(db)


async def finish(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    start: httpx2.Response,
    **provider_response: Any,
) -> httpx2.Response:
    """Approve a flow started earlier and follow the provider back."""

    return await client.get(
        fake_oauth.authorize(start.json()["authorization_url"], **provider_response)
    )


# --- Linking ------------------------------------------------------------------


async def test_linking_requires_a_recent_authentication(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    # A provider sign-in alone isn't fresh: its SSO may have answered.
    await sign_in(client, fake_oauth, "google", **approval("google"))

    response = await start_link(client, "github")

    assert response.status_code == 403
    assert error_code(response) == "reauthentication_required"


async def test_linking_adds_the_account_and_its_verified_email(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_recently(client, fake_oauth, db)

    response = await link(client, fake_oauth, "github", **approval("github"))

    assert frontend_redirect(response) == ("/settings", {"linked": "github"})
    methods = await sign_in_methods(client)
    assert [i["provider"] for i in methods["identities"]] == ["google", "github"]
    assert [(e["email"], e["is_primary"]) for e in methods["emails"]] == [
        ("Ada@Example.com", True),
        ("Octocat@GitHub.com", False),
    ]
    # One user: signing in with GitHub now lands in it.
    client.cookies.clear()
    await sign_in(client, fake_oauth, "github", **approval("github"))
    assert (await client.get("/api/auth/me")).json()["name"] == "Ada Lovelace"


async def test_a_provider_already_linked_cant_be_linked_again(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_recently(client, fake_oauth, db)

    response = await start_link(client, "google")

    assert response.status_code == 409
    assert error_code(response) == "provider_already_linked"


async def test_a_provider_linked_meanwhile_fails_at_the_callback(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_recently(client, fake_oauth, db)
    start = await start_link(client, "github")
    user_id = await db.scalar(select(UserSession.user_id))
    db.add(
        OAuthAccount(
            user_id=user_id, provider=OAuthProvider.GITHUB, provider_user_id="1"
        )
    )
    await db.flush()

    response = await finish(client, fake_oauth, start, **approval("github"))

    assert frontend_redirect(response) == (
        "/settings",
        {"error": "provider_already_linked"},
    )


async def test_an_account_linked_to_someone_else_is_refused(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(client, fake_oauth, "github", **approval("github"))
    client.cookies.clear()
    await signed_in_recently(client, fake_oauth, db)

    response = await link(client, fake_oauth, "github", **approval("github"))

    assert frontend_redirect(response) == ("/settings", {"error": "identity_in_use"})


async def test_an_email_someone_else_verified_isnt_attached(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(
        client,
        fake_oauth,
        "microsoft",
        claims={**MICROSOFT_CLAIMS, "email": "octocat@github.com"},
    )
    client.cookies.clear()
    await signed_in_recently(client, fake_oauth, db)

    response = await link(
        client,
        fake_oauth,
        "github",
        github_user=GITHUB_USER,
        github_emails=[{**GITHUB_EMAILS[1], "email": "octocat@GITHUB.COM"}],
    )

    assert frontend_redirect(response) == ("/settings", {"linked": "github"})
    assert await count_rows(db, UserEmail) == 2


async def test_a_flow_finished_by_another_user_fails(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    # Started as Ada; by the callback the browser is signed in as someone
    # else, who must not get Ada's link.
    await signed_in_recently(client, fake_oauth, db)
    start = await start_link(client, "github")
    await sign_in(client, fake_oauth, "microsoft", **approval("microsoft"))

    response = await finish(client, fake_oauth, start, **approval("github"))

    assert frontend_redirect(response) == ("/settings", {"error": "link_failed"})
    assert await count_rows(db, OAuthAccount) == 2


# --- Unlinking ----------------------------------------------------------------


async def test_unlinking_removes_the_account(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_recently(client, fake_oauth, db)
    await link(client, fake_oauth, "github", **approval("github"))

    response = await client.delete("/api/auth/identities/github")

    assert response.status_code == 204
    identities = (await sign_in_methods(client))["identities"]
    assert [i["provider"] for i in identities] == ["google"]


@pytest.mark.parametrize(
    ("provider", "status", "code"),
    [("google", 409, "last_method"), ("github", 404, "not_linked")],
)
async def test_unlinking_whats_not_there_to_spare_is_refused(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    provider: str,
    status: int,
    code: str,
) -> None:
    await signed_in_recently(client, fake_oauth, db)

    response = await client.delete(f"/api/auth/identities/{provider}")

    assert (response.status_code, error_code(response)) == (status, code)
    assert await count_rows(db, OAuthAccount) == 1
