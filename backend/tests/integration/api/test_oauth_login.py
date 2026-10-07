"""GET /api/auth/{provider}/login: sending the browser to the provider."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from tests.support.auth_flow import assert_oauth_failed
from tests.support.environment import APP_URL
from tests.support.fake_oauth import FakeOAuthServer


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
async def test_login_redirects_to_provider_with_pkce(
    client: httpx2.AsyncClient, provider: str, authorize_endpoint: str, scope: str
) -> None:
    response = await client.get(f"/api/auth/{provider}/login")

    assert response.status_code == 302
    url = urlsplit(response.headers["location"])
    params = {key: values[0] for key, values in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == authorize_endpoint
    assert params["response_type"] == "code"
    assert params["client_id"] == f"{provider}-client-id"
    assert params["redirect_uri"] == f"{APP_URL}/api/auth/{provider}/callback"
    assert params["scope"] == scope
    assert params["prompt"] == "select_account"
    assert params["code_challenge_method"] == "S256"
    assert len(params["code_challenge"]) == 43
    assert len(params["state"]) >= 20
    # OIDC providers get a nonce; GitHub has no ID token to carry one.
    assert ("nonce" in params) == (provider != "github")

    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("__host-http-oauth=")
    for attribute in ("httponly", "secure", "samesite=lax", "path=/", "max-age=600"):
        assert attribute in cookie
    assert "domain=" not in cookie


async def test_unreachable_provider_sends_user_back_with_an_error(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_oauth.unavailable_hosts.add("accounts.google.com")

    response = await client.get("/api/auth/google/login")

    assert_oauth_failed(response, caplog, "OAuth start failed for google")
