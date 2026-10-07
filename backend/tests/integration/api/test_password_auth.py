"""Email-and-password accounts over HTTP: /register, /register/complete,
/login, and reauthenticating with a password or an emailed link."""

from __future__ import annotations

import httpx2
import pytest
from argon2 import PasswordHasher
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import EmailToken, PasswordCredential
from app.modules.users.models import User, UserEmail
from tests.support.auth_flow import (
    EMAIL,
    PASSWORD,
    SESSION_COOKIE,
    approval,
    error_code,
    login,
    set_recently_authenticated,
    set_session_token,
    sign_in,
    sign_in_methods,
    sign_up,
)
from tests.support.database import MakeUser, count_rows
from tests.support.email import OutboxEmailSender
from tests.support.environment import APP_URL
from tests.support.fake_oauth import FakeOAuthServer
from tests.support.fake_pwned import BREACHED_PASSWORD


async def register(client: httpx2.AsyncClient, email: str = EMAIL) -> httpx2.Response:
    return await client.post("/api/auth/register", json={"email": email})


async def complete_registration(
    client: httpx2.AsyncClient, token: str, password: str = PASSWORD
) -> httpx2.Response:
    return await client.post(
        "/api/auth/register/complete",
        json={"token": token, "name": "Grace Hopper", "password": password},
    )


async def reauthenticate(client: httpx2.AsyncClient, password: str) -> httpx2.Response:
    return await client.post("/api/auth/reauthenticate", json={"password": password})


# --- Signing up ---------------------------------------------------------------


async def test_signing_up_by_email_link_creates_a_signed_in_account(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    requested = await register(client)

    assert requested.status_code == 202
    email = outbox.last_to(EMAIL)
    assert email.link().startswith(f"{APP_URL}/signup/complete#token=")
    assert email.idempotency_key.startswith("signup/")
    # Nothing exists until the link is opened.
    assert await count_rows(db, User) == 0

    completed = await complete_registration(client, email.token())

    assert completed.status_code == 204
    assert (await client.get("/api/auth/me")).json() == {
        "name": "Grace Hopper",
        "email": EMAIL,
        "avatar_url": None,
    }
    methods = await sign_in_methods(client)
    assert methods["has_password"] is True
    # A password plus a proven email is a fresh authentication.
    assert methods["recently_authenticated"] is True
    user_email = await db.scalar(select(UserEmail))
    assert user_email is not None
    assert user_email.is_primary


async def test_signing_up_with_a_taken_email_tells_only_its_owner(
    client: httpx2.AsyncClient,
    outbox: OutboxEmailSender,
    db: AsyncSession,
    make_user: MakeUser,
) -> None:
    await make_user(email=EMAIL)

    response = await register(client)

    # The same answer as for a free address; the email says the difference.
    assert response.status_code == 202
    assert outbox.last_to(EMAIL).subject == "You already have a CodeSpace account"
    assert await count_rows(db, EmailToken) == 0


async def test_an_invalid_email_is_refused(client: httpx2.AsyncClient) -> None:
    response = await register(client, "nope")

    assert response.status_code == 422
    assert error_code(response) == "invalid_email"


@pytest.mark.parametrize(
    ("password", "error"),
    [("too short", "password_too_short"), (BREACHED_PASSWORD, "password_breached")],
)
async def test_a_refused_password_leaves_the_link_usable(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, password: str, error: str
) -> None:
    refused = await sign_up(client, outbox, password=password)

    assert (refused.status_code, error_code(refused)) == (422, error)
    retried = await complete_registration(client, outbox.last_to(EMAIL).token())
    assert retried.status_code == 204


async def test_a_sign_up_link_works_once(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    response = await complete_registration(client, outbox.last_to(EMAIL).token())

    assert (response.status_code, error_code(response)) == (400, "invalid_token")


async def test_an_expired_sign_up_link_doesnt_work(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await register(client)
    await db.execute(update(EmailToken).values(expires_at=EmailToken.created_at))

    response = await complete_registration(client, outbox.last_to(EMAIL).token())

    assert response.status_code == 400


async def test_an_email_taken_meanwhile_isnt_signed_up_again(
    client: httpx2.AsyncClient,
    outbox: OutboxEmailSender,
    db: AsyncSession,
    make_user: MakeUser,
) -> None:
    await register(client)
    await make_user(email=EMAIL)

    response = await complete_registration(client, outbox.last_to(EMAIL).token())

    assert (response.status_code, error_code(response)) == (409, "account_exists")
    assert await count_rows(db, User) == 1


# --- Signing in ---------------------------------------------------------------


async def test_signing_in_with_a_password_starts_a_fresh_session(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)
    client.cookies.clear()

    response = await login(client, email="  grace@EXAMPLE.com")

    assert response.status_code == 204
    assert (await sign_in_methods(client))["recently_authenticated"] is True


async def test_every_failed_sign_in_gets_the_same_answer(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await sign_up(client, outbox)
    # Ada has an account with a verified email, but no password.
    await sign_in(client, fake_oauth, "google", **approval("google"))
    client.cookies.clear()

    responses = [
        await login(client, password="the wrong passphrase"),
        await login(client, email="nobody@example.com"),
        await login(client, email="Ada@Example.com"),
        await login(client, email="not an email"),
    ]

    assert {(r.status_code, r.text) for r in responses} == {(401, responses[0].text)}
    assert error_code(responses[0]) == "invalid_credentials"
    assert SESSION_COOKIE not in client.cookies


async def test_a_deactivated_user_cant_sign_in(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    await db.execute(update(User).values(is_active=False))

    assert (await login(client)).status_code == 401


async def test_failed_sign_ins_are_rate_limited_per_address(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    # Each failure is counted even though its request fails.
    for _ in range(10):
        await login(client, password="the wrong passphrase")

    response = await login(client)

    assert (response.status_code, error_code(response)) == (429, "rate_limited")
    assert int(response.headers["retry-after"]) > 0
    assert (await login(client, email="ada@example.com")).status_code == 401


async def test_a_password_hashed_with_old_parameters_is_upgraded(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    await db.execute(update(PasswordCredential).values(password_hash=weak))

    assert (await login(client)).status_code == 204

    db.expunge_all()
    upgraded = await db.scalar(select(PasswordCredential.password_hash))
    assert upgraded is not None
    assert "m=65536" in upgraded


# --- Reauthenticating ---------------------------------------------------------


async def test_reauthenticating_with_the_password_renews_the_session(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    await set_recently_authenticated(db, recent=False)
    old_token = client.cookies[SESSION_COOKIE]

    response = await reauthenticate(client, PASSWORD)

    assert response.status_code == 204
    assert client.cookies[SESSION_COOKIE] != old_token
    assert (await sign_in_methods(client))["recently_authenticated"] is True


async def test_a_wrong_password_doesnt_reauthenticate(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    await set_recently_authenticated(db, recent=False)

    response = await reauthenticate(client, "the wrong passphrase")

    assert response.status_code == 401
    assert (await sign_in_methods(client))["recently_authenticated"] is False


async def test_without_a_password_there_is_none_to_reauthenticate_with(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))

    assert (await reauthenticate(client, PASSWORD)).status_code == 401


async def test_reauthenticating_by_an_email_link(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))

    sent = await client.post("/api/auth/reauthenticate/email")

    assert sent.status_code == 202
    email = outbox.last_to("Ada@Example.com")
    assert email.link().startswith(f"{APP_URL}/reauthenticate#token=")
    response = await client.post(
        "/api/auth/reauthenticate/email/complete", json={"token": email.token()}
    )
    assert response.status_code == 204
    assert (await sign_in_methods(client))["recently_authenticated"] is True


async def test_an_email_link_works_only_in_the_browser_that_asked(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    # Ada asks for the link; someone else, signed in elsewhere, opens it.
    await sign_in(client, fake_oauth, "google", **approval("google"))
    adas_session = client.cookies[SESSION_COOKIE]
    await client.post("/api/auth/reauthenticate/email")
    body = {"token": outbox.last_to("Ada@Example.com").token()}
    client.cookies.clear()
    await sign_in(client, fake_oauth, "github", **approval("github"))

    elsewhere = await client.post("/api/auth/reauthenticate/email/complete", json=body)

    assert elsewhere.status_code == 400
    # Left unspent for Ada's own session.
    set_session_token(client, adas_session)
    own = await client.post("/api/auth/reauthenticate/email/complete", json=body)
    assert own.status_code == 204


async def test_only_the_newest_reauthentication_link_works(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))
    await client.post("/api/auth/reauthenticate/email")
    first = outbox.last_to("Ada@Example.com").token()
    await client.post("/api/auth/reauthenticate/email")

    response = await client.post(
        "/api/auth/reauthenticate/email/complete", json={"token": first}
    )

    assert (response.status_code, error_code(response)) == (400, "invalid_token")


async def test_email_reauthentication_needs_an_email(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await sign_in(
        client, fake_oauth, "google", claims={"sub": "no-email", "name": "Nameless"}
    )

    response = await client.post("/api/auth/reauthenticate/email")

    assert (response.status_code, error_code(response)) == (409, "no_email")
