"""The app as deployed: startup, health probes and HTTP security middleware."""

from __future__ import annotations

from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.support.environment import API_URL, FRONTEND_URL


@pytest.fixture
def started_app() -> Iterator[TestClient]:
    """The app with its real lifespan: its own engine on the test database,
    and no dependency overrides."""

    with TestClient(app, base_url=API_URL) as client:
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


async def test_cors_allows_the_frontend_with_credentials(
    client: httpx2.AsyncClient,
) -> None:
    response = await client.options(
        "/api/auth/me",
        headers={
            "origin": FRONTEND_URL,
            "access-control-request-method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_URL
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_cors_refuses_other_origins(client: httpx2.AsyncClient) -> None:
    response = await client.options(
        "/api/auth/me",
        headers={
            "origin": "https://evil.example",
            "access-control-request-method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
