"""Email-and-password accounts over HTTP: /register, /register/complete,
/login, and reauthenticating with a password or an emailed link."""

from __future__ import annotations

import logging

import httpx2
import pytest
from argon2 import PasswordHasher
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import (
    EmailToken,
    PasswordCredential,
    UserSession,
)
from app.modules.users.models import User, UserEmail
from tests.support.auth_flow import (
    PASSWORD,
    SESSION_COOKIE,
    approval,
    set_session_token,
    sign_in,
    sign_up,
)
from tests.support.database import MakeUser, count_rows
from tests.support.email import OutboxEmailSender
from tests.support.environment import APP_URL
from tests.support.fake_oauth import FakeOAuthServer
from tests.support.fake_pwned import BREACHED_PASSWORD

EMAIL = "grace@example.com"


def error_code(response: httpx2.Response) -> str:
    return response.json()["detail"]["code"]


async def methods(client: httpx2.AsyncClient) -> dict:
    return (await client.get("/api/auth/methods")).json()


async def login(
    client: httpx2.AsyncClient, email: str = EMAIL, password: str = PASSWORD
) -> httpx2.Response:
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


# --- Signing up ---------------------------------------------------------------


async def test_signing_up_emails_a_link_and_creates_nothing_yet(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    response = await client.post("/api/auth/register", json={"email": EMAIL})

    assert response.status_code == 202
    email = outbox.last_to(EMAIL)
    assert email.link().startswith(f"{APP_URL}/signup/complete#token=")
    assert email.idempotency_key.startswith("signup/")
    assert await count_rows(db, User) == 0


async def test_completing_sign_up_creates_a_signed_in_account(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    response = await sign_up(client, outbox)

    assert response.status_code == 204
    assert (await client.get("/api/auth/me")).json() == {
        "name": "Grace Hopper",
        "email": EMAIL,
        "avatar_url": None,
    }
    listed = await methods(client)
    assert listed["has_password"] is True
    # A password plus a proven email is a fresh authentication.
    assert listed["recently_authenticated"] is True
    email = await db.scalar(select(UserEmail))
    assert email is not None
    assert email.verified_at is not None
    assert email.is_primary


async def test_signing_up_with_a_taken_email_tells_only_its_owner(
    client: httpx2.AsyncClient,
    outbox: OutboxEmailSender,
    db: AsyncSession,
    make_user: MakeUser,
) -> None:
    await make_user(email=EMAIL)

    response = await client.post("/api/auth/register", json={"email": EMAIL})

    # The same answer as for a free address; the email says the difference.
    assert response.status_code == 202
    assert outbox.last_to(EMAIL).subject == "You already have a CodeSpace account"
    assert await count_rows(db, EmailToken) == 0


async def test_an_invalid_email_is_refused(client: httpx2.AsyncClient) -> None:
    response = await client.post("/api/auth/register", json={"email": "nope"})

    assert response.status_code == 422
    assert error_code(response) == "invalid_email"


async def test_sign_up_requests_are_rate_limited_per_address(
    client: httpx2.AsyncClient,
) -> None:
    for _ in range(3):
        await client.post("/api/auth/register", json={"email": EMAIL})

    response = await client.post("/api/auth/register", json={"email": EMAIL})

    assert response.status_code == 429
    assert error_code(response) == "rate_limited"
    assert int(response.headers["retry-after"]) > 0
    other = await client.post("/api/auth/register", json={"email": "ada@example.com"})
    assert other.status_code == 202


@pytest.mark.parametrize(
    ("password", "error"),
    [("too short", "password_too_short"), (BREACHED_PASSWORD, "password_breached")],
)
async def test_a_refused_password_leaves_the_link_usable(
    client: httpx2.AsyncClient,
    outbox: OutboxEmailSender,
    password: str,
    error: str,
) -> None:
    refused = await sign_up(client, outbox, password=password)

    assert refused.status_code == 422
    assert error_code(refused) == error
    retried = await client.post(
        "/api/auth/register/complete",
        json={
            "token": outbox.last_to(EMAIL).token(),
            "name": "G",
            "password": PASSWORD,
        },
    )
    assert retried.status_code == 204


async def test_a_sign_up_link_works_once(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)
    body = {"token": outbox.last_to(EMAIL).token(), "name": "G", "password": PASSWORD}

    response = await client.post("/api/auth/register/complete", json=body)

    assert response.status_code == 400
    assert error_code(response) == "invalid_token"


async def test_an_expired_sign_up_link_doesnt_work(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await client.post("/api/auth/register", json={"email": EMAIL})
    await db.execute(update(EmailToken).values(expires_at=EmailToken.created_at))

    response = await client.post(
        "/api/auth/register/complete",
        json={
            "token": outbox.last_to(EMAIL).token(),
            "name": "G",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 400


async def test_an_email_taken_meanwhile_isnt_signed_up_again(
    client: httpx2.AsyncClient,
    outbox: OutboxEmailSender,
    db: AsyncSession,
    make_user: MakeUser,
) -> None:
    await client.post("/api/auth/register", json={"email": EMAIL})
    await make_user(email=EMAIL)

    response = await client.post(
        "/api/auth/register/complete",
        json={
            "token": outbox.last_to(EMAIL).token(),
            "name": "G",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 409
    assert error_code(response) == "account_exists"
    assert await count_rows(db, User) == 1


# --- Signing in ---------------------------------------------------------------


async def test_signing_in_with_a_password_starts_a_fresh_session(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)
    client.cookies.clear()

    response = await login(client, email="  grace@EXAMPLE.com")

    assert response.status_code == 204
    assert SESSION_COOKIE in client.cookies
    assert (await methods(client))["recently_authenticated"] is True


async def test_signing_in_replaces_an_earlier_session(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    first = client.cookies[SESSION_COOKIE]

    await login(client)

    assert await count_rows(db, UserSession) == 1
    set_session_token(client, first)
    assert (await client.get("/api/auth/me")).status_code == 401


async def failed_logins(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> list[httpx2.Response]:
    await sign_up(client, outbox)
    # Ada has an account with a verified email, but no password.
    await sign_in(client, fake_oauth, "google", **approval("google"))
    client.cookies.clear()

    return [
        await login(client, password="the wrong passphrase"),
        await login(client, email="nobody@example.com"),
        await login(client, email="Ada@Example.com"),
        await login(client, email="not an email"),
    ]


async def test_every_failed_sign_in_gets_the_same_answer(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    responses = await failed_logins(client, fake_oauth, outbox)

    assert {response.status_code for response in responses} == {401}
    assert {response.text for response in responses} == {responses[0].text}
    assert error_code(responses[0]) == "invalid_credentials"
    assert SESSION_COOKIE not in client.cookies


async def test_an_inactive_user_cant_sign_in(
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
        assert (await login(client, password="wrong wrong wrong")).status_code == 401

    response = await login(client)

    assert response.status_code == 429
    assert error_code(response) == "rate_limited"


async def test_a_password_hashed_with_old_parameters_is_upgraded(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    await db.execute(update(PasswordCredential).values(password_hash=weak))

    assert (await login(client)).status_code == 204

    db.expunge_all()
    upgraded = await db.scalar(select(PasswordCredential.password_hash))
    assert upgraded != weak
    assert upgraded is not None
    assert "m=65536" in upgraded


# --- Reauthenticating ---------------------------------------------------------


async def stale(db: AsyncSession) -> None:
    await db.execute(update(UserSession).values(authenticated_at=None))


async def test_reauthenticating_with_the_password(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    await stale(db)
    old_token = client.cookies[SESSION_COOKIE]

    response = await client.post(
        "/api/auth/reauthenticate", json={"password": PASSWORD}
    )

    assert response.status_code == 204
    assert client.cookies[SESSION_COOKIE] != old_token
    assert (await methods(client))["recently_authenticated"] is True


async def test_a_wrong_password_doesnt_reauthenticate(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender, db: AsyncSession
) -> None:
    await sign_up(client, outbox)
    await stale(db)

    response = await client.post(
        "/api/auth/reauthenticate", json={"password": "the wrong passphrase"}
    )

    assert response.status_code == 401
    assert (await methods(client))["recently_authenticated"] is False


async def test_without_a_password_there_is_none_to_reauthenticate_with(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))

    response = await client.post(
        "/api/auth/reauthenticate", json={"password": PASSWORD}
    )

    assert response.status_code == 401


async def test_password_reauthentication_is_rate_limited(
    client: httpx2.AsyncClient, outbox: OutboxEmailSender
) -> None:
    await sign_up(client, outbox)

    for _ in range(10):
        await client.post("/api/auth/reauthenticate", json={"password": "wrong"})

    response = await client.post(
        "/api/auth/reauthenticate", json={"password": PASSWORD}
    )

    assert response.status_code == 429


async def test_reauthenticating_by_email_link_in_the_same_browser(
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
    assert (await methods(client))["recently_authenticated"] is True


async def test_an_email_link_opened_in_another_browser_doesnt_count(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
) -> None:
    # Ada asks for the link; someone else signed in elsewhere opens it.
    await sign_in(client, fake_oauth, "google", **approval("google"))
    adas_session = client.cookies[SESSION_COOKIE]
    await client.post("/api/auth/reauthenticate/email")
    token = outbox.last_to("Ada@Example.com").token()
    client.cookies.clear()
    await sign_in(client, fake_oauth, "github", **approval("github"))

    elsewhere = await client.post(
        "/api/auth/reauthenticate/email/complete", json={"token": token}
    )

    assert elsewhere.status_code == 400
    # Left unspent for Ada's own session.
    set_session_token(client, adas_session)
    own = await client.post(
        "/api/auth/reauthenticate/email/complete", json={"token": token}
    )
    assert own.status_code == 204


async def test_email_reauthentication_needs_an_email(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await sign_in(
        client, fake_oauth, "google", claims={"sub": "no-email", "name": "Nameless"}
    )

    response = await client.post("/api/auth/reauthenticate/email")

    assert response.status_code == 409
    assert error_code(response) == "no_email"


# --- The password as a sign-in method -----------------------------------------


async def test_with_a_password_the_last_provider_can_be_unlinked(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    outbox: OutboxEmailSender,
    db: AsyncSession,
) -> None:
    await sign_up(client, outbox)
    await db.execute(
        update(UserSession).values(authenticated_at=UserSession.created_at)
    )
    start = await client.post("/api/auth/github/link")
    await client.get(
        fake_oauth.authorize(start.json()["authorization_url"], **approval("github"))
    )

    response = await client.delete("/api/auth/identities/github")

    assert response.status_code == 204


async def test_password_events_are_audited(
    client: httpx2.AsyncClient,
    outbox: OutboxEmailSender,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.auth.audit")

    await sign_up(client, outbox)
    await login(client, password="the wrong passphrase")
    await login(client)

    events = [r.event for r in caplog.records if r.name == "app.auth.audit"]
    assert events == [
        "auth.signup.requested",
        "auth.signup.completed",
        "auth.login.failed",
        "auth.login.succeeded",
    ]
    assert PASSWORD not in caplog.text
