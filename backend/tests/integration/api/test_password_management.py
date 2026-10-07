"""Managing a password over HTTP: resetting a forgotten one, adding one to a
provider-only account, changing it and removing it."""

from __future__ import annotations

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import PasswordCredential, UserSession
from tests.support.auth_flow import (
    EMAIL,
    PASSWORD,
    SESSION_COOKIE,
    approval,
    error_code,
    link,
    login,
    set_recently_authenticated,
    set_session_token,
    sign_in,
    sign_in_methods,
    sign_up,
)
from tests.support.database import count_rows
from tests.support.email import OutboxEmailSender
from tests.support.environment import APP_URL
from tests.support.fake_oauth import FakeOAuthServer

NEW_PASSWORD = "an entirely new passphrase"
ADA = "Ada@Example.com"


async def forgot(client: httpx2.AsyncClient, email: str = EMAIL) -> httpx2.Response:
    return await client.post("/api/auth/password/forgot", json={"email": email})


async def reset(client: httpx2.AsyncClient, token: str) -> httpx2.Response:
    return await client.post(
        "/api/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}
    )


async def complete_setup(client: httpx2.AsyncClient, token: str) -> httpx2.Response:
    return await client.post(
        "/api/auth/password/setup/complete",
        json={"token": token, "password": NEW_PASSWORD},
    )


async def change(client: httpx2.AsyncClient, current: str) -> httpx2.Response:
    return await client.post(
        "/api/auth/password/change",
        json={"current_password": current, "new_password": NEW_PASSWORD},
    )


async def google_user_recently(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    """Signed in with Google only, and as if just reauthenticated."""

    await sign_in(client, fake_oauth, "google", **approval("google"))
    await set_recently_authenticated(db)


# --- Resetting a forgotten password -------------------------------------------


async def test_resetting_replaces_the_password_and_signs_out_everywhere(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    old_session = client.cookies[SESSION_COOKIE]

    requested = await forgot(client, "grace@EXAMPLE.com")

    assert requested.status_code == 202
    email = outbox.last_to(EMAIL)
    assert email.link().startswith(f"{APP_URL}/reset-password#token=")
    assert (await reset(client, email.token())).status_code == 204
    assert await count_rows(db, UserSession) == 0
    set_session_token(client, old_session)
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await login(client)).status_code == 401
    assert (await login(client, password=NEW_PASSWORD)).status_code == 204


async def test_no_link_goes_out_without_a_password_account(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))

    unknown = await forgot(client, "nobody@example.com")
    provider_only = await forgot(client, ADA)

    # The same answer as when a link goes out.
    assert unknown.status_code == provider_only.status_code == 202
    assert outbox.sent == []


async def test_only_the_newest_reset_link_works(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)
    await forgot(client)
    first = outbox.last_to(EMAIL).token()
    await forgot(client)

    response = await reset(client, first)

    assert (response.status_code, error_code(response)) == (400, "invalid_token")
    assert (await reset(client, outbox.last_to(EMAIL).token())).status_code == 204


# --- Adding a password --------------------------------------------------------


async def test_a_provider_only_account_adds_a_password_by_email_link(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
    db: AsyncSession,
) -> None:
    await google_user_recently(client, fake_oauth, db)

    started = await client.post("/api/auth/password/setup")

    assert started.status_code == 202
    email = outbox.last_to(ADA)
    assert email.link().startswith(f"{APP_URL}/password-setup#token=")
    assert (await complete_setup(client, email.token())).status_code == 204
    assert (await sign_in_methods(client))["has_password"] is True
    assert (await login(client, ADA, NEW_PASSWORD)).status_code == 204


async def test_a_password_cant_be_added_twice(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await client.post("/api/auth/password/setup")

    assert (response.status_code, error_code(response)) == (409, "password_exists")


async def test_a_setup_link_doesnt_replace_a_password_added_meanwhile(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
    db: AsyncSession,
) -> None:
    await google_user_recently(client, fake_oauth, db)
    await client.post("/api/auth/password/setup")
    user_id = await db.scalar(select(UserSession.user_id))
    db.add(PasswordCredential(user_id=user_id, password_hash="$argon2id$elsewhere"))
    await db.flush()

    response = await complete_setup(client, outbox.last_to(ADA).token())

    assert (response.status_code, error_code(response)) == (409, "password_exists")


async def test_a_password_needs_an_email(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(
        client, fake_oauth, "google", claims={"sub": "no-email", "name": "Nameless"}
    )
    await set_recently_authenticated(db)

    response = await client.post("/api/auth/password/setup")

    assert (response.status_code, error_code(response)) == (409, "no_email")


# --- Changing the password ----------------------------------------------------


async def test_changing_the_password_signs_out_other_sessions_only(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    other_browser = client.cookies[SESSION_COOKIE]
    client.cookies.clear()
    await login(client)

    response = await change(client, PASSWORD)

    assert response.status_code == 204
    assert await count_rows(db, UserSession) == 1
    set_session_token(client, other_browser)
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await login(client, password=NEW_PASSWORD)).status_code == 204


async def test_changing_needs_the_current_password(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await change(client, "not the current passphrase")

    assert response.status_code == 401
    assert (await login(client)).status_code == 204


# --- Removing the password ----------------------------------------------------


async def test_removing_the_password_keeps_the_linked_provider(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await sign_up(client, outbox)
    await link(client, fake_oauth, "github", **approval("github"))

    response = await client.delete("/api/auth/password")

    assert response.status_code == 204
    assert (await sign_in_methods(client))["has_password"] is False
    assert (await login(client)).status_code == 401


async def test_the_only_sign_in_method_cant_be_removed(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await client.delete("/api/auth/password")

    assert (response.status_code, error_code(response)) == (409, "last_method")


async def test_removing_a_password_there_isnt_is_not_found(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await google_user_recently(client, fake_oauth, db)

    response = await client.delete("/api/auth/password")

    assert (response.status_code, error_code(response)) == (404, "no_password")
