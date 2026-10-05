"""Managing a password over HTTP: forgetting and resetting it, adding one to
a provider-only account, changing it and removing it."""

from __future__ import annotations

import logging

import httpx2
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import PasswordCredential, UserSession
from tests.support.auth_flow import (
    PASSWORD,
    SESSION_COOKIE,
    approval,
    complete_flow,
    set_session_token,
    sign_in,
    sign_up,
)
from tests.support.database import count_rows
from tests.support.email import OutboxEmailSender
from tests.support.environment import APP_URL
from tests.support.fake_oauth import FakeOAuthServer

EMAIL = "grace@example.com"
NEW_PASSWORD = "an entirely new passphrase"


def error_code(response: httpx2.Response) -> str:
    return response.json()["detail"]["code"]


async def login(
    client: httpx2.AsyncClient, password: str, email: str = EMAIL
) -> httpx2.Response:
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


async def has_password(client: httpx2.AsyncClient) -> bool:
    return (await client.get("/api/auth/methods")).json()["has_password"]


async def forgot(client: httpx2.AsyncClient, email: str = EMAIL) -> httpx2.Response:
    return await client.post("/api/auth/password/forgot", json={"email": email})


async def reset(
    client: httpx2.AsyncClient, token: str, password: str = NEW_PASSWORD
) -> httpx2.Response:
    return await client.post(
        "/api/auth/password/reset", json={"token": token, "password": password}
    )


async def stale(db: AsyncSession) -> None:
    await db.execute(update(UserSession).values(authenticated_at=None))


# --- Forgetting and resetting -------------------------------------------------


async def test_a_forgotten_password_gets_a_reset_link(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await forgot(client, "grace@EXAMPLE.com")

    assert response.status_code == 202
    email = outbox.last_to(EMAIL)
    assert email.link().startswith(f"{APP_URL}/reset-password#token=")
    assert email.idempotency_key.startswith("password-reset/")


async def test_no_link_goes_out_without_a_password_account(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))

    unknown = await forgot(client, "nobody@example.com")
    provider_only = await forgot(client, "Ada@Example.com")

    # The same answer as when a link goes out.
    assert unknown.status_code == provider_only.status_code == 202
    assert outbox.sent == []


async def test_reset_requests_are_rate_limited(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    for _ in range(3):
        await forgot(client)

    response = await forgot(client)

    assert response.status_code == 429


async def test_resetting_replaces_the_password_and_signs_out_everywhere(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    old_session = client.cookies[SESSION_COOKIE]
    await forgot(client)

    response = await reset(client, outbox.last_to(EMAIL).token())

    assert response.status_code == 204
    assert SESSION_COOKIE not in client.cookies
    assert await count_rows(db, UserSession) == 0
    set_session_token(client, old_session)
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await login(client, PASSWORD)).status_code == 401
    assert (await login(client, NEW_PASSWORD)).status_code == 204


async def test_only_the_newest_reset_link_works(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)
    await forgot(client)
    first = outbox.last_to(EMAIL).token()
    await forgot(client)
    second = outbox.last_to(EMAIL).token()

    assert (await reset(client, first)).status_code == 400
    assert (await reset(client, second)).status_code == 204


async def test_a_reset_link_works_once(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)
    await forgot(client)
    token = outbox.last_to(EMAIL).token()
    await reset(client, token)

    response = await reset(client, token, "yet another fine passphrase")

    assert response.status_code == 400
    assert error_code(response) == "invalid_token"


async def test_a_refused_new_password_leaves_the_reset_link_usable(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)
    await forgot(client)
    token = outbox.last_to(EMAIL).token()

    refused = await reset(client, token, "short")

    assert error_code(refused) == "password_too_short"
    assert (await reset(client, token)).status_code == 204


# --- Adding a password --------------------------------------------------------


async def test_adding_a_password_requires_a_recent_authentication(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))

    response = await client.post("/api/auth/password/setup")

    assert response.status_code == 403
    assert error_code(response) == "reauthentication_required"


async def test_a_provider_only_account_adds_a_password_by_email_link(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await confirmed_google_user(client, fake_oauth)

    started = await client.post("/api/auth/password/setup")

    assert started.status_code == 202
    email = outbox.last_to("Ada@Example.com")
    assert email.link().startswith(f"{APP_URL}/password-setup#token=")
    completed = await complete_setup(client, email.token())
    assert completed.status_code == 204
    assert await has_password(client)
    client.cookies.clear()
    assert (await login(client, NEW_PASSWORD, "Ada@Example.com")).status_code == 204


async def test_a_password_cant_be_added_twice(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await client.post("/api/auth/password/setup")

    assert response.status_code == 409
    assert error_code(response) == "password_exists"


async def confirmed_google_user(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))
    await complete_flow(
        client, fake_oauth, "google", "reauthenticate", **approval("google")
    )


async def complete_setup(
    client: httpx2.AsyncClient, token: str, password: str = NEW_PASSWORD
) -> httpx2.Response:
    return await client.post(
        "/api/auth/password/setup/complete",
        json={"token": token, "password": password},
    )


async def test_only_the_newest_setup_link_works(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await confirmed_google_user(client, fake_oauth)
    await client.post("/api/auth/password/setup")
    first = outbox.last_to("Ada@Example.com").token()
    await client.post("/api/auth/password/setup")

    assert (await complete_setup(client, first)).status_code == 400


async def test_a_setup_link_doesnt_replace_a_password_added_meanwhile(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
    db: AsyncSession,
) -> None:
    await confirmed_google_user(client, fake_oauth)
    await client.post("/api/auth/password/setup")
    user_id = await db.scalar(select(UserSession.user_id))
    db.add(PasswordCredential(user_id=user_id, password_hash="$argon2id$elsewhere"))
    await db.flush()

    response = await complete_setup(client, outbox.last_to("Ada@Example.com").token())

    assert response.status_code == 409
    assert error_code(response) == "password_exists"


async def test_a_password_needs_an_email(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(
        client, fake_oauth, "google", claims={"sub": "no-email", "name": "Nameless"}
    )
    await db.execute(
        update(UserSession).values(authenticated_at=UserSession.created_at)
    )

    response = await client.post("/api/auth/password/setup")

    assert response.status_code == 409
    assert error_code(response) == "no_email"


# --- Changing the password ----------------------------------------------------


async def change(
    client: httpx2.AsyncClient, current: str, new: str = NEW_PASSWORD
) -> httpx2.Response:
    return await client.post(
        "/api/auth/password/change",
        json={"current_password": current, "new_password": new},
    )


async def test_changing_the_password_signs_out_other_sessions_only(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    other_browser = client.cookies[SESSION_COOKIE]
    client.cookies.clear()
    await login(client, PASSWORD)
    await stale(db)

    response = await change(client, PASSWORD)

    assert response.status_code == 204
    assert await count_rows(db, UserSession) == 1
    methods = (await client.get("/api/auth/methods")).json()
    assert methods["recently_authenticated"] is True
    set_session_token(client, other_browser)
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await login(client, PASSWORD)).status_code == 401
    assert (await login(client, NEW_PASSWORD)).status_code == 204


async def test_changing_needs_the_current_password(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await change(client, "not the current passphrase")

    assert response.status_code == 401
    assert (await login(client, PASSWORD)).status_code == 204


async def test_a_refused_new_password_changes_nothing(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await change(client, PASSWORD, "short")

    assert error_code(response) == "password_too_short"
    assert (await login(client, PASSWORD)).status_code == 204


# --- Removing the password ----------------------------------------------------


async def with_password_and_github(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await sign_up(client, outbox)
    await complete_flow(client, fake_oauth, "github", "link", **approval("github"))


async def test_removing_the_password(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await with_password_and_github(client, fake_oauth, outbox)

    response = await client.delete("/api/auth/password")

    assert response.status_code == 204
    assert not await has_password(client)
    assert (await login(client, PASSWORD)).status_code == 401


async def test_removing_requires_a_recent_authentication(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
    db: AsyncSession,
) -> None:
    await with_password_and_github(client, fake_oauth, outbox)
    await stale(db)

    response = await client.delete("/api/auth/password")

    assert response.status_code == 403


async def test_the_only_sign_in_method_cant_be_removed(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await client.delete("/api/auth/password")

    assert response.status_code == 409
    assert error_code(response) == "last_method"
    assert await has_password(client)


async def test_removing_a_password_there_isnt_is_not_found(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))
    await db.execute(
        update(UserSession).values(authenticated_at=UserSession.created_at)
    )

    response = await client.delete("/api/auth/password")

    assert response.status_code == 404


async def test_password_management_is_audited(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await with_password_and_github(client, fake_oauth, outbox)
    caplog.set_level(logging.INFO, logger="app.auth.audit")

    await change(client, PASSWORD)
    await client.delete("/api/auth/password")
    await forgot(client)

    events = [r.event for r in caplog.records if r.name == "app.auth.audit"]
    assert events == [
        "auth.password.changed",
        "auth.password.removed",
        "auth.password.reset_requested",
    ]
