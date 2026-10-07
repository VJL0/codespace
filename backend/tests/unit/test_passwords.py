"""The password policy and the Pwned Passwords check."""

from __future__ import annotations

import logging

import httpx2
import pytest
from fastapi import HTTPException

from app.modules.auth.passwords import check_password_policy
from tests.support.fake_pwned import BREACHED_PASSWORD, FakePwnedPasswords


@pytest.fixture
def fake_pwned() -> FakePwnedPasswords:
    return FakePwnedPasswords()


@pytest.fixture
def http_client(fake_pwned: FakePwnedPasswords) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=fake_pwned.transport)


async def policy_error(password: str, http_client: httpx2.AsyncClient) -> str | None:
    try:
        await check_password_policy(password, http_client)
    except HTTPException as exc:
        return exc.detail["code"]

    return None


@pytest.mark.parametrize(
    ("password", "error"),
    [
        ("x" * 14, "password_too_short"),
        ("x" * 15, None),
        ("x" * 256, None),
        ("x" * 257, "password_too_long"),
        # No composition rules, and any Unicode is allowed.
        ("🔐 mot de passe très long", None),
        # Length counts NFC characters: "e" + U+0301 (combining acute) is "é".
        ("e\u0301" * 15, None),
        ("e\u0301" * 14, "password_too_short"),
        (BREACHED_PASSWORD, "password_breached"),
    ],
)
async def test_policy(
    http_client: httpx2.AsyncClient, password: str, error: str | None
) -> None:
    assert await policy_error(password, http_client) == error


async def test_only_a_padded_hash_prefix_leaves_the_server(
    http_client: httpx2.AsyncClient, fake_pwned: FakePwnedPasswords
) -> None:
    await policy_error(BREACHED_PASSWORD, http_client)

    [request] = fake_pwned.requests
    assert len(request.url.path.rsplit("/", 1)[-1]) == 5
    assert request.headers["add-padding"] == "true"
    assert BREACHED_PASSWORD not in str(request.url)


async def test_the_breach_check_fails_open(
    http_client: httpx2.AsyncClient,
    fake_pwned: FakePwnedPasswords,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_pwned.available = False
    caplog.set_level(logging.INFO, logger="app.auth.audit")

    assert await policy_error(BREACHED_PASSWORD, http_client) is None
    assert "auth.password.breach_check_unavailable" in caplog.text
