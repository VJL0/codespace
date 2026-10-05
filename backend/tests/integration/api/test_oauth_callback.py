"""GET /api/auth/{provider}/callback: signing in with the provider's answer.

Runs the real flow (Authlib, PKCE, ID token signature and claim checks)
against the in-process fake providers.
"""

from __future__ import annotations

from typing import Any

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

PROVIDERS = ["google", "microsoft", "github"]


# --- Successful sign-in -----------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "provider_user_id", "email", "name", "avatar_url"),
    [
        (
            "google",
            GOOGLE_CLAIMS["sub"],
            "Ada@Example.com",
            "Ada Lovelace",
            GOOGLE_CLAIMS["picture"],
        ),
        (
            "microsoft",
            f"{MICROSOFT_OID}.{MICROSOFT_ORG_TENANT}",
            "grace@contoso.com",
            "Grace Hopper",
            None,
        ),
        (
            "github",
            "583231",
            "Octocat@GitHub.com",
            "The Octocat",
            GITHUB_USER["avatar_url"],
        ),
    ],
)
async def test_sign_in_creates_user_account_and_session(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    provider: str,
    provider_user_id: str,
    email: str,
    name: str,
    avatar_url: str | None,
) -> None:
    response = await sign_in(client, fake_oauth, provider, **approval(provider))

    assert frontend_error(response) is None
    assert response.headers["location"] == f"{APP_URL}/"

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"name": name, "email": email, "avatar_url": avatar_url}

    account = await db.scalar(select(OAuthAccount))
    assert account is not None
    assert account.provider.value == provider
    assert account.provider_user_id == provider_user_id
    assert account.email_snapshot == email


async def test_google_accepts_issuer_without_scheme(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer
) -> None:
    # Google documents both "https://accounts.google.com" and "accounts.google.com".
    response = await sign_in(
        client,
        fake_oauth,
        "google",
        claims={**GOOGLE_CLAIMS, "iss": "accounts.google.com"},
    )

    assert frontend_error(response) is None


async def test_microsoft_personal_account_signs_in(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    claims = {
        **MICROSOFT_CLAIMS,
        "tid": MICROSOFT_PERSONAL_TENANT,
        "email": "grace@outlook.com",
    }

    response = await sign_in(
        client,
        fake_oauth,
        "microsoft",
        claims=claims,
        signing_key=MICROSOFT_PERSONAL_KEY,
    )

    assert frontend_error(response) is None
    account = await db.scalar(select(OAuthAccount))
    assert account is not None
    assert account.provider_user_id == f"{MICROSOFT_OID}.{MICROSOFT_PERSONAL_TENANT}"


async def test_signing_in_again_replaces_the_session(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(client, fake_oauth, "google", claims=GOOGLE_CLAIMS)
    first_token = client.cookies[SESSION_COOKIE]

    response = await sign_in(client, fake_oauth, "google", claims=GOOGLE_CLAIMS)

    assert frontend_error(response) is None
    assert client.cookies[SESSION_COOKIE] != first_token
    assert await count_rows(db, UserSession) == 1

    set_session_token(client, first_token)
    assert (await client.get("/api/auth/me")).status_code == 401


# --- Sign-ins without an email ------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "provider_response"),
    [
        ("google", {"claims": {**GOOGLE_CLAIMS, "email_verified": False}}),
        (
            "microsoft",
            {"claims": {k: v for k, v in MICROSOFT_CLAIMS.items() if k != "xms_edov"}},
        ),
        ("microsoft", {"claims": {**MICROSOFT_CLAIMS, "xms_edov": False}}),
        (
            "github",
            {
                "github_user": GITHUB_USER,
                "github_emails": [{**GITHUB_EMAILS[1], "verified": False}],
            },
        ),
        ("github", {"github_user": GITHUB_USER, "github_emails": [GITHUB_EMAILS[0]]}),
        (
            "microsoft",
            {"claims": {k: v for k, v in MICROSOFT_CLAIMS.items() if k != "email"}},
        ),
    ],
    ids=[
        "google",
        "microsoft-no-xms_edov",
        "microsoft-xms_edov-false",
        "github",
        "github-no-primary-email",
        "microsoft-no-email",
    ],
)
async def test_sign_in_without_a_verified_email_leaves_the_user_without_one(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    provider: str,
    provider_response: dict[str, Any],
) -> None:
    # Sign-in rests on the provider's user ID; an email it doesn't vouch for
    # is never recorded as the user's.
    response = await sign_in(client, fake_oauth, provider, **provider_response)

    assert frontend_error(response) is None
    assert (await client.get("/api/auth/me")).json()["email"] is None
    assert await count_rows(db, User) == 1
    assert await count_rows(db, UserEmail) == 0


# --- Refused sign-ins ---------------------------------------------------------


async def test_same_email_from_another_provider_is_refused(
    client: httpx2.AsyncClient, fake_oauth: FakeOAuthServer, db: AsyncSession
) -> None:
    await sign_in(client, fake_oauth, "google", claims=GOOGLE_CLAIMS)
    client.cookies.clear()

    response = await sign_in(
        client,
        fake_oauth,
        "github",
        github_user=GITHUB_USER,
        # Ada@Example.com in another letter case: the domain's doesn't matter.
        github_emails=[{**GITHUB_EMAILS[1], "email": "Ada@EXAMPLE.COM"}],
    )

    assert frontend_error(response) == "account_exists"
    assert await count_rows(db, User) == 1
    assert await count_rows(db, OAuthAccount) == 1


async def test_github_profile_without_a_user_id_fails(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
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
    assert await count_rows(db, User) == 0


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
            {
                "claims": {
                    **GOOGLE_CLAIMS,
                    "aud": "another-client",
                    "azp": "google-client-id",
                }
            },
            "Invalid claim: 'aud'",
            id="id-token-aud-wrong-azp-right",
        ),
        pytest.param(
            {
                "claims": {
                    **GOOGLE_CLAIMS,
                    "aud": ["google-client-id", "another-client"],
                }
            },
            "Invalid claim: 'aud'",
            id="id-token-untrusted-extra-audience",
        ),
        pytest.param(
            {"claims": {**GOOGLE_CLAIMS, "nonce": "replayed"}},
            "Invalid claim: 'nonce'",
            id="id-token-nonce-wrong",
        ),
        pytest.param(
            {"claims": {**GOOGLE_CLAIMS, "exp": 1_000_000_000}},
            "The token is expired",
            id="id-token-expired",
        ),
        pytest.param(
            {"error": "access_denied"}, "access_denied", id="user-denied-consent"
        ),
    ],
)
async def test_google_callback_rejections(
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
            {**MICROSOFT_CLAIMS, "tid": MICROSOFT_ORG_TENANT.upper()},
            MICROSOFT_ORG_KEY,
            "Invalid claim: 'iss'",
            id="tid-not-canonical-guid",
        ),
        pytest.param(
            {k: v for k, v in MICROSOFT_CLAIMS.items() if k != "tid"},
            MICROSOFT_ORG_KEY,
            "Missing claim: 'tid'",
            id="tid-missing",
        ),
        pytest.param(
            {
                **MICROSOFT_CLAIMS,
                "iss": "https://login.microsoftonline.com/{tenantid}/v2.0",
            },
            MICROSOFT_ORG_KEY,
            "Invalid claim: 'iss'",
            id="iss-template-literal",
        ),
        pytest.param(
            {k: v for k, v in MICROSOFT_CLAIMS.items() if k != "oid"},
            MICROSOFT_ORG_KEY,
            "Microsoft returned no `oid` claim",
            id="oid-missing",
        ),
    ],
)
async def test_microsoft_callback_rejections(
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


async def test_callback_from_another_browser_fails(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Login CSRF: an attacker's own callback URL replayed in the victim's
    # browser has no matching state in the victim's OAuth cookie.
    login = await client.get("/api/auth/google/login")
    callback = fake_oauth.authorize(login.headers["location"], claims=GOOGLE_CLAIMS)
    client.cookies.clear()

    assert_oauth_failed(await client.get(callback), caplog, "mismatching_state")
    assert await count_rows(db, User) == 0


# --- Provider failures --------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "host"),
    [
        # The token exchange, common to all providers, and GitHub's profile
        # API, which only its adapter calls.
        pytest.param("google", "oauth2.googleapis.com", id="token-endpoint"),
        pytest.param("github", "api.github.com", id="github-api"),
    ],
)
async def test_provider_outage_during_callback_fails(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    db: AsyncSession,
    caplog: pytest.LogCaptureFixture,
    provider: str,
    host: str,
) -> None:
    login = await client.get(f"/api/auth/{provider}/login")
    callback = fake_oauth.authorize(login.headers["location"], **approval(provider))
    fake_oauth.unavailable_hosts.add(host)

    response = await client.get(callback)

    assert_oauth_failed(response, caplog, f"OAuth callback failed for {provider}")
    assert await count_rows(db, User) == 0
