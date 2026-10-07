"""The app as deployed: startup, health probes and HTTP security middleware."""

from __future__ import annotations

from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.support.environment import APP_URL


@pytest.fixture
def started_app() -> Iterator[TestClient]:
    """The app with its real lifespan: its own engine on the test database,
    and no dependency overrides."""

    with TestClient(app, base_url=APP_URL) as client:
        yield client


def test_readiness_probe_reaches_the_database(started_app: TestClient) -> None:
    response = started_app.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == "ok"


async def test_unknown_host_is_rejected(client: httpx2.AsyncClient) -> None:
    response = await client.get("/health/live", headers={"host": "evil.example"})

    assert response.status_code == 400


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_api_docs_are_only_served_in_development(
    client: httpx2.AsyncClient, path: str
) -> None:
    assert (await client.get(path)).status_code == 404


async def test_api_sends_no_cors_headers(client: httpx2.AsyncClient) -> None:
    # The SPA and API share an origin; no other origin may read responses.
    response = await client.options(
        "/api/auth/me",
        headers={
            "origin": "https://evil.example",
            "access-control-request-method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


async def test_each_response_carries_a_generated_request_id(
    client: httpx2.AsyncClient,
) -> None:
    first = await client.get("/health/live")
    second = await client.get("/health/live")

    assert len(first.headers["x-request-id"]) == 32
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


async def test_the_edge_request_id_is_kept(client: httpx2.AsyncClient) -> None:
    response = await client.get(
        "/health/live", headers={"x-request-id": "edge-1234.abc_DEF"}
    )

    assert response.headers["x-request-id"] == "edge-1234.abc_DEF"


@pytest.mark.parametrize("request_id", ["has spaces", "x" * 129, "a/b<script>"])
async def test_a_malformed_request_id_is_replaced(
    client: httpx2.AsyncClient, request_id: str
) -> None:
    response = await client.get("/health/live", headers={"x-request-id": request_id})

    assert response.headers["x-request-id"] != request_id
    assert len(response.headers["x-request-id"]) == 32
