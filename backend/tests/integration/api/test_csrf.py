"""The same-origin check every state-changing /api request must pass."""

from __future__ import annotations

import httpx2
import pytest

from tests.support.environment import APP_URL

# POST /api/auth/logout changes state and needs no session, so it shows the
# check alone: 204 when it passes, 403 when it doesn't.
LOGOUT = "/api/auth/logout"


async def post_with(client: httpx2.AsyncClient, **headers: str) -> httpx2.Response:
    """POST logout with exactly these headers, not the client's defaults."""

    client.headers.clear()

    return await client.post(LOGOUT, headers=headers)


async def test_spa_request_passes(client: httpx2.AsyncClient) -> None:
    response = await post_with(
        client, **{"x-csrf-protection": "1", "sec-fetch-site": "same-origin"}
    )

    assert response.status_code == 204


async def test_missing_custom_header_is_refused(client: httpx2.AsyncClient) -> None:
    # A plain cross-site form post can't add custom headers.
    response = await post_with(client, **{"sec-fetch-site": "same-origin"})

    assert response.status_code == 403


@pytest.mark.parametrize("fetch_site", ["cross-site", "same-site", "none"])
async def test_request_not_from_this_origin_is_refused(
    client: httpx2.AsyncClient, fetch_site: str
) -> None:
    # same-site: a sibling subdomain is still another origin.
    response = await post_with(
        client, **{"x-csrf-protection": "1", "sec-fetch-site": fetch_site}
    )

    assert response.status_code == 403


async def test_fetch_metadata_wins_over_a_matching_origin(
    client: httpx2.AsyncClient,
) -> None:
    response = await post_with(
        client,
        **{"x-csrf-protection": "1", "sec-fetch-site": "cross-site", "origin": APP_URL},
    )

    assert response.status_code == 403


async def test_without_fetch_metadata_the_app_origin_passes(
    client: httpx2.AsyncClient,
) -> None:
    response = await post_with(client, **{"x-csrf-protection": "1", "origin": APP_URL})

    assert response.status_code == 204


@pytest.mark.parametrize(
    "origin", [None, "null", "https://evil.example", f"{APP_URL}.evil.example"]
)
async def test_without_fetch_metadata_any_other_origin_is_refused(
    client: httpx2.AsyncClient, origin: str | None
) -> None:
    headers = {"x-csrf-protection": "1"}

    if origin is not None:
        headers["origin"] = origin

    response = await post_with(client, **headers)

    assert response.status_code == 403


async def test_safe_methods_are_not_checked(client: httpx2.AsyncClient) -> None:
    client.headers.clear()

    # 401, not 403: the request reached the endpoint.
    assert (await client.get("/api/auth/me")).status_code == 401
