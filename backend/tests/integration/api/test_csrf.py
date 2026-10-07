"""The same-origin check every state-changing /api request must pass."""

from __future__ import annotations

import httpx2
import pytest

from tests.support.environment import APP_URL


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        pytest.param({"sec-fetch-site": "same-origin"}, 204, id="spa"),
        pytest.param({"origin": APP_URL}, 204, id="no-fetch-metadata"),
        # A plain cross-site form post, or a no-cors fetch().
        pytest.param({"sec-fetch-site": "cross-site"}, 403, id="cross"),
        # A sibling subdomain is same-site, but still another origin.
        pytest.param({"sec-fetch-site": "same-site"}, 403, id="sibling"),
        # Typed in the address bar or opened from a bookmark: never a POST
        # the app sends.
        pytest.param({"sec-fetch-site": "none"}, 403, id="user-initiated"),
        pytest.param(
            {"sec-fetch-site": "cross-site", "origin": APP_URL},
            403,
            id="fetch-metadata-wins",
        ),
        pytest.param({}, 403, id="no-origin"),
        pytest.param({"origin": f"{APP_URL}.evil.example"}, 403, id="lookalike-origin"),
    ],
)
async def test_state_changing_requests_must_come_from_the_app(
    client: httpx2.AsyncClient, headers: dict[str, str], status: int
) -> None:
    client.headers.clear()

    # Logout changes state and needs no session, so it shows the check alone.
    response = await client.post("/api/auth/logout", headers=headers)

    assert response.status_code == status


async def test_safe_methods_are_not_checked(client: httpx2.AsyncClient) -> None:
    client.headers.clear()

    # 401, not 403: the request reached the endpoint.
    assert (await client.get("/api/auth/me")).status_code == 401
