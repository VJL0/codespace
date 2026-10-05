"""Provider responses and helpers for driving sign-in through the HTTP API."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from tests.support.environment import APP_HOST, APP_URL
from tests.support.fake_oauth import MICROSOFT_ORG_TENANT, FakeOAuthServer

SESSION_COOKIE = "__Host-Http-session"

# What a browser sends with the SPA's same-origin fetch() calls.
SAME_ORIGIN_HEADERS = {"x-csrf-protection": "1", "sec-fetch-site": "same-origin"}

GOOGLE_CLAIMS = {
    "sub": "110169484474386276334",
    "email": "Ada@Example.com",
    "email_verified": True,
    "name": "Ada Lovelace",
    "picture": "https://lh3.googleusercontent.com/a/ada",
}
MICROSOFT_OID = "00000000-0000-0000-66f3-3332eca7ea81"
MICROSOFT_CLAIMS = {
    "sub": "pairwise-subject",
    "oid": MICROSOFT_OID,
    "tid": MICROSOFT_ORG_TENANT,
    "email": "grace@contoso.com",
    "xms_edov": True,
    "name": "Grace Hopper",
}
GITHUB_USER = {
    "id": 583231,
    "login": "octocat",
    "name": "The Octocat",
    "avatar_url": "https://avatars.githubusercontent.com/u/583231",
}
GITHUB_EMAILS = [
    {
        "email": "old@example.com",
        "primary": False,
        "verified": True,
        "visibility": None,
    },
    {
        "email": "Octocat@GitHub.com",
        "primary": True,
        "verified": True,
        "visibility": "public",
    },
]


def approval(provider: str) -> dict[str, Any]:
    """A successful sign-in's provider response, as `authorize` kwargs."""

    if provider == "github":
        return {"github_user": GITHUB_USER, "github_emails": GITHUB_EMAILS}

    return {"claims": GOOGLE_CLAIMS if provider == "google" else MICROSOFT_CLAIMS}


async def sign_in(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    provider: str,
    **provider_response: Any,
) -> httpx2.Response:
    login = await client.get(f"/api/auth/{provider}/login")
    assert login.status_code == 302, login.text

    return await client.get(
        fake_oauth.authorize(login.headers["location"], **provider_response)
    )


async def start_flow(
    client: httpx2.AsyncClient, provider: str, purpose: str
) -> httpx2.Response:
    """POST /api/auth/{provider}/{purpose}: start a link or reauthentication,
    which answers with the provider URL to send the browser to."""

    return await client.post(f"/api/auth/{provider}/{purpose}")


async def complete_flow(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    provider: str,
    purpose: str,
    **provider_response: Any,
) -> httpx2.Response:
    """Start a link or reauthentication, approve it at the provider and
    return the callback's response."""

    start = await start_flow(client, provider, purpose)
    assert start.status_code == 200, start.text

    return await client.get(
        fake_oauth.authorize(start.json()["authorization_url"], **provider_response)
    )


def set_session_token(client: httpx2.AsyncClient, token: str) -> None:
    client.cookies.set(SESSION_COOKIE, token, domain=APP_HOST)


def frontend_redirect(response: httpx2.Response) -> tuple[str, dict[str, str]]:
    """The SPA path and query a redirect back to the frontend carries."""

    assert response.status_code == 303, response.text
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == APP_URL

    return location.path, {
        key: values[0] for key, values in parse_qs(location.query).items()
    }


def frontend_error(response: httpx2.Response) -> str | None:
    """The `error` a redirect back to the frontend carries, or None."""

    return frontend_redirect(response)[1].get("error")


def assert_oauth_failed(
    response: httpx2.Response, caplog: pytest.LogCaptureFixture, reason: str
) -> None:
    # The reason is checked so a test can't pass on some unrelated failure.
    assert frontend_error(response) == "oauth_failed"
    assert reason in caplog.text, caplog.text
