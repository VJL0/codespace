"""Password policy, hashing and the Pwned Passwords check."""

from __future__ import annotations

import logging

import httpx2
import pytest
from argon2 import PasswordHasher

from app.modules.auth.passwords import (
    PasswordPolicyError,
    check_password_policy,
    hash_password,
    needs_rehash,
    verify_password,
)
from tests.support.fake_pwned import BREACHED_PASSWORD, FakePwnedPasswords

GOOD_PASSWORD = "a perfectly fine passphrase"


@pytest.fixture
def fake_pwned() -> FakePwnedPasswords:
    return FakePwnedPasswords()


@pytest.fixture
async def http_client(fake_pwned: FakePwnedPasswords) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=fake_pwned.transport)


async def policy_error(password: str, http_client: httpx2.AsyncClient) -> str | None:
    try:
        await check_password_policy(password, http_client)
    except PasswordPolicyError as exc:
        return exc.code

    return None


@pytest.mark.parametrize(
    ("password", "error"),
    [
        ("x" * 14, "password_too_short"),
        ("x" * 15, None),
        ("x" * 256, None),
        ("x" * 257, "password_too_long"),
        # No composition rules: one long run of lowercase letters is fine.
        ("abcdefghijklmnopqrstuvwxyz", None),
        # Spaces and any Unicode are allowed.
        ("🔐 mot de passe très long", None),
    ],
)
async def test_length_is_the_only_rule_besides_breaches(
    http_client: httpx2.AsyncClient, password: str, error: str | None
) -> None:
    assert await policy_error(password, http_client) == error


async def test_length_counts_normalized_characters(
    http_client: httpx2.AsyncClient,
) -> None:
    # "ﬁ" (one ligature character) is "fi" (two) under NFKC.
    assert await policy_error("ﬁ" * 8, http_client) is None


async def test_a_breached_password_is_refused(
    http_client: httpx2.AsyncClient, fake_pwned: FakePwnedPasswords
) -> None:
    assert await policy_error(BREACHED_PASSWORD, http_client) == "password_breached"

    # k-anonymity: only a 5-character hash prefix leaves, with padding asked for.
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


async def test_a_hash_verifies_its_password_only() -> None:
    password_hash = await hash_password(GOOD_PASSWORD)

    assert password_hash.startswith("$argon2id$")
    assert GOOD_PASSWORD not in password_hash
    assert await verify_password(password_hash, GOOD_PASSWORD)
    assert not await verify_password(password_hash, GOOD_PASSWORD.upper())


async def test_verification_normalizes_the_password() -> None:
    password_hash = await hash_password("ﬁne passphrase here")

    assert await verify_password(password_hash, "fine passphrase here")


@pytest.mark.parametrize("password_hash", [None, "not-a-hash"])
async def test_without_a_valid_hash_nothing_verifies(password_hash: str | None) -> None:
    assert not await verify_password(password_hash, GOOD_PASSWORD)


async def test_hashes_with_old_parameters_need_rehashing() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)

    assert needs_rehash(weak.hash(GOOD_PASSWORD))
    assert not needs_rehash(await hash_password(GOOD_PASSWORD))
