from __future__ import annotations

import hashlib
import logging
import unicodedata

import httpx2
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from starlette.concurrency import run_in_threadpool

from app.modules.auth.audit import audit

logger = logging.getLogger(__name__)

# Argon2id with argon2-cffi's defaults (RFC 9106's low-memory profile: 64
# MiB, 3 passes, 4 lanes), above OWASP's minimum. Changing them later is
# safe: each hash records its own, and check_needs_rehash() upgrades old
# ones at the next sign-in.
_hasher = PasswordHasher()

# Verified when the account has no password, so a missing account takes as
# long to reject as a wrong password.
_DUMMY_HASH = _hasher.hash("not anyone's password")

MIN_LENGTH = 15
MAX_LENGTH = 256


class PasswordPolicyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _normalize(password: str) -> str:
    # NIST SP 800-63B: the same password typed on another keyboard or OS
    # should match.
    return unicodedata.normalize("NFKC", password)


async def check_password_policy(password: str, http_client: httpx2.AsyncClient) -> None:
    """Raise PasswordPolicyError unless `password` may be set.

    NIST SP 800-63B-4 for a password used alone: long enough, no
    composition rules, and not known from breaches.
    """

    length = len(_normalize(password))

    if length < MIN_LENGTH:
        raise PasswordPolicyError(
            "password_too_short", f"Use at least {MIN_LENGTH} characters."
        )

    if length > MAX_LENGTH:
        raise PasswordPolicyError(
            "password_too_long", f"Use at most {MAX_LENGTH} characters."
        )

    if await _is_breached(password, http_client):
        raise PasswordPolicyError(
            "password_breached",
            "This password has appeared in a data breach. Choose another.",
        )


async def _is_breached(password: str, http_client: httpx2.AsyncClient) -> bool:
    """Whether Have I Been Pwned knows the password, by k-anonymity: only the
    first 5 hex digits of its SHA-1 leave this server, and padding hides how
    many hashes share them. Fails open: an outage mustn't block sign-ups."""

    digest = hashlib.sha1(_normalize(password).encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]

    try:
        response = await http_client.get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            headers={"Add-Padding": "true"},
            timeout=3,
        )
        response.raise_for_status()
    except httpx2.HTTPError as exc:
        logger.warning("Pwned Passwords check failed: %r", exc)
        audit("auth.password.breach_check_unavailable")
        return False

    for line in response.text.splitlines():
        candidate, _, count = line.partition(":")

        # Padding entries have a count of 0.
        if candidate == suffix and int(count or 0) > 0:
            return True

    return False


async def hash_password(password: str) -> str:
    # Deliberately slow and memory-hard: off the event loop.
    return await run_in_threadpool(_hasher.hash, _normalize(password))


async def verify_password(password_hash: str | None, password: str) -> bool:
    """Whether `password` matches; with no hash, still spends the time of a
    check, then fails."""

    try:
        await run_in_threadpool(
            _hasher.verify, password_hash or _DUMMY_HASH, _normalize(password)
        )
    except VerificationError, InvalidHashError:
        return False

    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
