"""Linking and unlinking provider accounts, and the reauthentication that
guards both: /api/auth/{provider}/link, /{provider}/reauthenticate,
/identities/{provider} and /methods."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx2
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OAuthAccount, OAuthProvider, UserSession
from app.modules.users.models import UserEmail
from tests.support.auth_flow import (
    GITHUB_EMAILS,
    GITHUB_USER,
    GOOGLE_CLAIMS,
    MICROSOFT_CLAIMS,
    SESSION_COOKIE,
    approval,
    complete_flow,
    frontend_redirect,
    set_session_token,
    sign_in,
    start_flow,
)
from tests.support.database import count_rows
from tests.support.fake_oauth import FakeOAuthServer


async def signed_in_with_google(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))


async def mark_recently_authenticated(db: AsyncSession) -> None:
    """As if the session had just reauthenticated."""

    await db.execute(update(UserSession).values(authenticated_at=func.now()))


async def methods(client: httpx2.AsyncClient) -> dict:
    response = await client.get("/api/auth/methods")
    assert response.status_code == 200, response.text

    return response.json()


def error_code(response: httpx2.Response) -> str:
    return response.json()["detail"]["code"]


# --- Reauthentication ---------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "forcing_param"),
    [("google", ("max_age", "0")), ("microsoft", ("prompt", "login"))],
)
async def test_reauthentication_forces_credentials_and_makes_the_session_recent(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    provider: str,
    forcing_param: tuple[str, str],
) -> None:
    await sign_in(client, fake_oauth, provider, **approval(provider))
    old_token = client.cookies[SESSION_COOKIE]
    assert (await methods(client))["recently_authenticated"] is False

    response = await complete_flow(
        client, fake_oauth, provider, "reauthenticate", **approval(provider)
    )

    assert frontend_redirect(response) == (
        "/settings",
        {"reauthenticated": provider},
    )
    key, value = forcing_param
    assert fake_oauth.authorizations[-1][key] == value
    assert (await methods(client))["recently_authenticated"] is True

    # The renewed token replaces the old one.
    assert client.cookies[SESSION_COOKIE] != old_token
    set_session_token(client, old_token)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_github_cant_reauthenticate(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await sign_in(client, fake_oauth, "github", **approval("github"))

    response = await start_flow(client, "github", "reauthenticate")

    assert response.status_code == 400
    assert error_code(response) == "reauth_unsupported"


async def test_reauthentication_needs_a_linked_account(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await signed_in_with_google(client, fake_oauth)

    response = await start_flow(client, "microsoft", "reauthenticate")

    assert response.status_code == 409
    assert error_code(response) == "not_linked"


async def test_reauthentication_needs_a_session(client: httpx2.AsyncClient) -> None:
    assert (await start_flow(client, "google", "reauthenticate")).status_code == 401


async def test_stale_auth_time_is_rejected(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    # The provider answered from an old sign-in despite max_age=0.
    await signed_in_with_google(client, fake_oauth)
    an_hour_ago = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())

    response = await complete_flow(
        client,
        fake_oauth,
        "google",
        "reauthenticate",
        claims={**GOOGLE_CLAIMS, "auth_time": an_hour_ago},
    )

    assert frontend_redirect(response) == ("/settings", {"error": "reauth_failed"})
    assert (await methods(client))["recently_authenticated"] is False


async def test_stripping_the_forcing_parameter_doesnt_work(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    # Someone at an unattended browser removes prompt=login from the URL, so
    # Microsoft answers from its SSO session, without an auth_time.
    await sign_in(client, fake_oauth, "microsoft", **approval("microsoft"))
    start = await start_flow(client, "microsoft", "reauthenticate")
    url = urlsplit(start.json()["authorization_url"])
    params = {k: v[0] for k, v in parse_qs(url.query).items() if k != "prompt"}
    tampered = urlunsplit(url._replace(query=urlencode(params)))

    response = await client.get(fake_oauth.authorize(tampered, **approval("microsoft")))

    assert frontend_redirect(response) == ("/settings", {"error": "reauth_failed"})
    assert (await methods(client))["recently_authenticated"] is False


async def test_reauthenticating_as_someone_else_fails(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    await signed_in_with_google(client, fake_oauth)

    response = await complete_flow(
        client,
        fake_oauth,
        "google",
        "reauthenticate",
        claims={**GOOGLE_CLAIMS, "sub": "another-google-account"},
    )

    assert frontend_redirect(response) == ("/settings", {"error": "reauth_failed"})


async def test_reauthentication_finished_by_another_user_fails(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    # Started as Ada; by the callback the browser is signed in as someone
    # else, whose session must not be the one made recent.
    await signed_in_with_google(client, fake_oauth)
    start = await start_flow(client, "google", "reauthenticate")
    await sign_in(client, fake_oauth, "github", **approval("github"))

    response = await client.get(
        fake_oauth.authorize(start.json()["authorization_url"], **approval("google"))
    )

    assert frontend_redirect(response) == ("/settings", {"error": "reauth_failed"})
    assert (await methods(client))["recently_authenticated"] is False


# --- Linking ------------------------------------------------------------------


async def test_linking_requires_a_recent_authentication(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    # A provider sign-in alone isn't fresh: its SSO may have answered.
    await signed_in_with_google(client, fake_oauth)

    response = await start_flow(client, "github", "link")

    assert response.status_code == 403
    assert error_code(response) == "reauthentication_required"


async def test_linking_needs_a_session(client: httpx2.AsyncClient) -> None:
    assert (await start_flow(client, "github", "link")).status_code == 401


async def test_linking_adds_the_account_and_its_verified_email(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)

    response = await complete_flow(
        client, fake_oauth, "github", "link", **approval("github")
    )

    assert frontend_redirect(response) == ("/settings", {"linked": "github"})
    linked = await methods(client)
    assert [i["provider"] for i in linked["identities"]] == ["google", "github"]
    assert [(e["email"], e["is_primary"]) for e in linked["emails"]] == [
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
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)

    response = await start_flow(client, "google", "link")

    assert response.status_code == 409
    assert error_code(response) == "provider_already_linked"


async def test_a_provider_linked_meanwhile_fails_at_the_callback(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)
    start = await start_flow(client, "github", "link")
    user_id = await db.scalar(select(UserSession.user_id))
    db.add(
        OAuthAccount(
            user_id=user_id, provider=OAuthProvider.GITHUB, provider_user_id="1"
        )
    )
    await db.flush()

    response = await client.get(
        fake_oauth.authorize(start.json()["authorization_url"], **approval("github"))
    )

    assert frontend_redirect(response) == (
        "/settings",
        {"error": "provider_already_linked"},
    )


async def test_an_account_linked_to_someone_else_is_refused(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(client, fake_oauth, "github", **approval("github"))
    client.cookies.clear()
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)

    response = await complete_flow(
        client, fake_oauth, "github", "link", **approval("github")
    )

    assert frontend_redirect(response) == ("/settings", {"error": "identity_in_use"})
    assert await count_rows(db, OAuthAccount) == 2


async def test_a_linked_email_someone_else_verified_isnt_attached(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(
        client,
        fake_oauth,
        "microsoft",
        claims={**MICROSOFT_CLAIMS, "email": "octocat@github.com"},
    )
    client.cookies.clear()
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)

    response = await complete_flow(
        client,
        fake_oauth,
        "github",
        "link",
        github_user=GITHUB_USER,
        github_emails=[{**GITHUB_EMAILS[1], "email": "octocat@GITHUB.COM"}],
    )

    assert frontend_redirect(response) == ("/settings", {"linked": "github"})
    assert await count_rows(db, UserEmail) == 2


async def test_linking_finished_by_another_user_fails(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)
    start = await start_flow(client, "github", "link")
    await sign_in(client, fake_oauth, "microsoft", **approval("microsoft"))

    response = await client.get(
        fake_oauth.authorize(start.json()["authorization_url"], **approval("github"))
    )

    assert frontend_redirect(response) == ("/settings", {"error": "link_failed"})
    assert await count_rows(db, OAuthAccount) == 2


async def test_cancelled_linking_returns_to_settings(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)

    response = await complete_flow(
        client, fake_oauth, "github", "link", error="access_denied"
    )

    assert frontend_redirect(response) == ("/settings", {"error": "oauth_failed"})


# --- Unlinking ----------------------------------------------------------------


async def linked_google_and_github(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)
    await complete_flow(client, fake_oauth, "github", "link", **approval("github"))


async def test_unlinking_removes_the_account(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await linked_google_and_github(client, fake_oauth, db)

    response = await client.delete("/api/auth/identities/github")

    assert response.status_code == 204
    assert [i["provider"] for i in (await methods(client))["identities"]] == ["google"]


async def test_unlinking_requires_a_recent_authentication(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await linked_google_and_github(client, fake_oauth, db)
    await db.execute(update(UserSession).values(authenticated_at=None))

    response = await client.delete("/api/auth/identities/github")

    assert response.status_code == 403
    assert error_code(response) == "reauthentication_required"


async def test_the_last_sign_in_method_cant_be_unlinked(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)

    response = await client.delete("/api/auth/identities/google")

    assert response.status_code == 409
    assert error_code(response) == "last_method"
    assert await count_rows(db, OAuthAccount) == 1


async def test_unlinking_an_unlinked_provider_is_not_found(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await signed_in_with_google(client, fake_oauth)
    await mark_recently_authenticated(db)

    response = await client.delete("/api/auth/identities/github")

    assert response.status_code == 404
    assert error_code(response) == "not_linked"


# --- Sign-in methods ----------------------------------------------------------


async def test_methods_list_reauthentication_providers_and_recency(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await linked_google_and_github(client, fake_oauth, db)

    listed = await methods(client)

    # GitHub can't force a credential prompt, so it can't confirm it's you.
    assert listed["reauthentication_providers"] == ["google"]
    assert listed["recently_authenticated"] is True
    assert listed["identities"][0]["email_snapshot"] == "Ada@Example.com"


async def test_methods_need_a_session(client: httpx2.AsyncClient) -> None:
    assert (await client.get("/api/auth/methods")).status_code == 401
