"""Signing in with Google, Microsoft or GitHub: /api/auth/{provider}/login and
/callback, run for real (Authlib, PKCE, ID token signature and claim checks)
against the in-process fake providers."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OAuthAccount, UserSession
from app.modules.users.models import User, UserEmail
from tests.support.auth_flow import (
    GITHUB_EMAILS,
    GITHUB_USER,
    GOOGLE_CLAIMS,
    MICROSOFT_CLAIMS,
    MICROSOFT_OID,
    SESSION_COOKIE,
    approval,
    assert_oauth_failed,
    frontend_error,
    frontend_redirect,
    set_session_token,
    sign_in,
)
from tests.support.database import count_rows
from tests.support.environment import APP_URL
from tests.support.fake_oauth import (
    MICROSOFT_ORG_KEY,
    MICROSOFT_ORG_TENANT,
    MICROSOFT_PERSONAL_KEY,
    MICROSOFT_PERSONAL_TENANT,
    FakeOAuthServer,
)

ADA = {
    "name": "Ada Lovelace",
    "email": "Ada@Example.com",
    "avatar_url": GOOGLE_CLAIMS["picture"],
}
GRACE = {"name": "Grace Hopper", "email": "grace@contoso.com", "avatar_url": None}
OCTOCAT = {
    "name": "The Octocat",
    "email": "Octocat@GitHub.com",
    "avatar_url": GITHUB_USER["avatar_url"],
}


def cookie_attributes(response: httpx2.Response, name: str) -> set[str]:
    [cookie] = [
        c for c in response.headers.get_list("set-cookie") if c.startswith(name)
    ]

    return {part.strip().lower() for part in cookie.split(";")[1:]}


# --- Starting ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "authorize_endpoint", "scope"),
    [
        (
            "google",
            "https://accounts.google.com/o/oauth2/v2/auth",
            "openid email profile",
        ),
        (
            "microsoft",
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "openid email profile",
        ),
        ("github", "https://github.com/login/oauth/authorize", "read:user user:email"),
    ],
)
async def test_login_redirects_to_the_provider_with_pkce(
    client: httpx2.AsyncClient, provider: str, authorize_endpoint: str, scope: str
) -> None:
    response = await client.get(f"/api/auth/{provider}/login")

    assert response.status_code == 302
    url = urlsplit(response.headers["location"])
    params = {key: values[0] for key, values in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == authorize_endpoint
    assert params["client_id"] == f"{provider}-client-id"
    assert params["redirect_uri"] == f"{APP_URL}/api/auth/{provider}/callback"
    assert params["scope"] == scope
    assert params["prompt"] == "select_account"
    assert params["code_challenge_method"] == "S256"
    # OIDC providers get a nonce; GitHub has no ID token to carry one.
    assert ("nonce" in params) == (provider != "github")
    assert {"httponly", "secure", "samesite=lax", "path=/", "max-age=600"} <= (
        cookie_attributes(response, "__Host-Http-oauth")
    )


async def test_an_unreachable_provider_sends_the_user_back_with_an_error(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_oauth.unavailable_hosts.add("accounts.google.com")

    response = await client.get("/api/auth/google/login")

    assert_oauth_failed(response, caplog, "OAuth start failed for google")


# --- Signing in ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "provider_response", "provider_user_id", "me"),
    [
        pytest.param(
            "google", approval("google"), GOOGLE_CLAIMS["sub"], ADA, id="google"
        ),
        # Google documents both "https://accounts.google.com" and this.
        pytest.param(
            "google",
            {"claims": {**GOOGLE_CLAIMS, "iss": "accounts.google.com"}},
            GOOGLE_CLAIMS["sub"],
            ADA,
            id="google-issuer-without-scheme",
        ),
        pytest.param(
            "microsoft",
            approval("microsoft"),
            f"{MICROSOFT_OID}.{MICROSOFT_ORG_TENANT}",
            GRACE,
            id="microsoft-work-account",
        ),
        pytest.param(
            "microsoft",
            {
                "claims": {**MICROSOFT_CLAIMS, "tid": MICROSOFT_PERSONAL_TENANT},
                "signing_key": MICROSOFT_PERSONAL_KEY,
            },
            f"{MICROSOFT_OID}.{MICROSOFT_PERSONAL_TENANT}",
            GRACE,
            id="microsoft-personal-account",
        ),
        pytest.param("github", approval("github"), "583231", OCTOCAT, id="github"),
    ],
)
async def test_sign_in_creates_the_user_their_account_and_a_session(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    provider: str,
    provider_response: dict[str, Any],
    provider_user_id: str,
    me: dict[str, str | None],
) -> None:
    response = await sign_in(client, fake_oauth, provider, **provider_response)

    assert frontend_redirect(response) == ("/", {})
    assert (await client.get("/api/auth/me")).json() == me
    account = await db.scalar(select(OAuthAccount))
    assert account is not None
    assert (account.provider.value, account.provider_user_id) == (
        provider,
        provider_user_id,
    )


async def test_the_session_cookie_is_host_only_secure_and_http_only(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    response = await sign_in(client, fake_oauth, "google", **approval("google"))

    attributes = cookie_attributes(response, SESSION_COOKIE)
    assert {"httponly", "secure", "samesite=lax", "path=/"} <= attributes
    # The __Host- prefix forbids a Domain; browsers drop the cookie otherwise.
    assert not any(attribute.startswith("domain=") for attribute in attributes)


async def test_signing_in_again_replaces_the_session(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))
    first_token = client.cookies[SESSION_COOKIE]

    await sign_in(client, fake_oauth, "google", **approval("google"))

    assert await count_rows(db, UserSession) == 1
    set_session_token(client, first_token)
    assert (await client.get("/api/auth/me")).status_code == 401


@pytest.mark.parametrize(
    ("provider", "provider_response"),
    [
        ("google", {"claims": {**GOOGLE_CLAIMS, "email_verified": False}}),
        (
            "microsoft",
            {"claims": {k: v for k, v in MICROSOFT_CLAIMS.items() if k != "xms_edov"}},
        ),
        ("github", {"github_user": GITHUB_USER, "github_emails": [GITHUB_EMAILS[0]]}),
    ],
    ids=["google-unverified", "microsoft-without-xms_edov", "github-no-primary"],
)
async def test_an_email_the_provider_doesnt_vouch_for_isnt_recorded(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    provider: str,
    provider_response: dict[str, Any],
) -> None:
    response = await sign_in(client, fake_oauth, provider, **provider_response)

    assert frontend_error(response) is None
    assert (await client.get("/api/auth/me")).json()["email"] is None
    assert await count_rows(db, UserEmail) == 0


async def test_an_email_another_user_verified_is_refused(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))
    client.cookies.clear()

    response = await sign_in(
        client,
        fake_oauth,
        "github",
        github_user=GITHUB_USER,
        # Ada@Example.com with the domain in another case: still the same.
        github_emails=[{**GITHUB_EMAILS[1], "email": "Ada@EXAMPLE.COM"}],
    )

    assert frontend_error(response) == "account_exists"
    assert await count_rows(db, User) == 1


# --- Refused sign-ins ---------------------------------------------------------


@pytest.mark.parametrize(
    ("provider_response", "reason"),
    [
        pytest.param(
            {"claims": GOOGLE_CLAIMS, "iss": None},
            "Authorization response issuer mismatch",
            id="rfc9207-iss-missing",
        ),
        pytest.param(
            {"claims": GOOGLE_CLAIMS, "iss": "https://evil.example"},
            "Authorization response issuer mismatch",
            id="rfc9207-iss-wrong",
        ),
        pytest.param(
            {"claims": {**GOOGLE_CLAIMS, "iss": "https://evil.example"}},
            "Invalid claim: 'iss'",
            id="id-token-iss-wrong",
        ),
        pytest.param(
            {"claims": {**GOOGLE_CLAIMS, "aud": "another-client"}},
            "Invalid claim: 'aud'",
            id="id-token-aud-wrong",
        ),
        pytest.param(
            {"claims": {**GOOGLE_CLAIMS, "aud": ["google-client-id", "another"]}},
            "Invalid claim: 'aud'",
            id="id-token-untrusted-extra-audience",
        ),
        pytest.param({"error": "access_denied"}, "access_denied", id="denied"),
    ],
)
async def test_google_answers_that_are_refused(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    caplog: pytest.LogCaptureFixture,
    provider_response: dict[str, Any],
    reason: str,
) -> None:
    response = await sign_in(client, fake_oauth, "google", **provider_response)

    assert_oauth_failed(response, caplog, reason)
    assert await count_rows(db, User) == 0


@pytest.mark.parametrize(
    ("claims", "signing_key", "reason"),
    [
        # A work/school tenant's token signed with the personal-accounts key.
        pytest.param(
            MICROSOFT_CLAIMS,
            MICROSOFT_PERSONAL_KEY,
            "Invalid claim: 'iss'",
            id="org-token-personal-key",
        ),
        pytest.param(
            {
                **MICROSOFT_CLAIMS,
                "iss": f"https://login.microsoftonline.com/{MICROSOFT_PERSONAL_TENANT}/v2.0",
            },
            MICROSOFT_ORG_KEY,
            "Invalid claim: 'iss'",
            id="iss-tid-mismatch",
        ),
        pytest.param(
            {**MICROSOFT_CLAIMS, "tid": "not-a-guid"},
            MICROSOFT_ORG_KEY,
            "Invalid claim: 'iss'",
            id="tid-not-guid",
        ),
        pytest.param(
            {k: v for k, v in MICROSOFT_CLAIMS.items() if k != "tid"},
            MICROSOFT_ORG_KEY,
            "Invalid claim: 'iss'",
            id="tid-missing",
        ),
        pytest.param(
            {k: v for k, v in MICROSOFT_CLAIMS.items() if k != "oid"},
            MICROSOFT_ORG_KEY,
            "Microsoft returned no `oid` claim",
            id="oid-missing",
        ),
    ],
)
async def test_microsoft_answers_that_are_refused(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    caplog: pytest.LogCaptureFixture,
    claims: dict[str, Any],
    signing_key: str,
    reason: str,
) -> None:
    response = await sign_in(
        client, fake_oauth, "microsoft", claims=claims, signing_key=signing_key
    )

    assert_oauth_failed(response, caplog, reason)
    assert await count_rows(db, User) == 0


async def test_a_github_profile_without_a_user_id_is_refused(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = await sign_in(
        client,
        fake_oauth,
        "github",
        github_user={k: v for k, v in GITHUB_USER.items() if k != "id"},
        github_emails=GITHUB_EMAILS,
    )

    assert_oauth_failed(response, caplog, "GitHub returned no user ID")


async def test_a_callback_from_another_browser_is_refused(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Login CSRF: an attacker's own callback URL replayed in the victim's
    # browser has no matching state in the victim's OAuth cookie.
    login = await client.get("/api/auth/google/login")
    callback = fake_oauth.authorize(login.headers["location"], claims=GOOGLE_CLAIMS)
    client.cookies.clear()

    assert_oauth_failed(await client.get(callback), caplog, "mismatching_state")


@pytest.mark.parametrize(
    ("provider", "host"),
    [
        # The token exchange, common to all providers, and GitHub's profile
        # API, which only its adapter calls.
        pytest.param("google", "oauth2.googleapis.com", id="token-endpoint"),
        pytest.param("github", "api.github.com", id="github-api"),
    ],
)
async def test_a_provider_outage_during_the_callback_is_reported(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    caplog: pytest.LogCaptureFixture,
    provider: str,
    host: str,
) -> None:
    login = await client.get(f"/api/auth/{provider}/login")
    callback = fake_oauth.authorize(login.headers["location"], **approval(provider))
    fake_oauth.unavailable_hosts.add(host)

    response = await client.get(callback)

    assert_oauth_failed(response, caplog, f"OAuth callback failed for {provider}")
