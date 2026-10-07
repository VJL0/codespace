from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import RateLimitCounter
from app.modules.users.emails import EmailNotValidError, normalize_email


class RateLimitedError(Exception):
    def __init__(self, retry_after: timedelta) -> None:
        super().__init__("Too many attempts.")
        self.retry_after = retry_after


def email_key(scope: str, address: str) -> str:
    """The bucket for attempts on one email address, keyed by an HMAC of it
    so the table holds no addresses."""

    try:
        canonical = normalize_email(address)
    except EmailNotValidError:
        canonical = address.strip()

    digest = hmac.new(
        settings.rate_limit_secret_key.encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()

    return f"{scope}:email:{digest}"


def ip_key(scope: str, request: Request) -> str:
    """The bucket for attempts from the client's network: its IPv4 address,
    or its IPv6 /64, which one subscriber typically gets whole."""

    host = request.client.host if request.client else "unknown"

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return f"{scope}:ip:{host}"

    if address.version == 6:
        return f"{scope}:ip:{ipaddress.ip_network(f'{address}/64', strict=False)}"

    return f"{scope}:ip:{address}"


class RateLimiter:
    """Fixed-window counters in PostgreSQL, shared by every app worker.

    It slows guessing down and never locks an account: the window simply
    passes. Commit after hit() so failed attempts count even when the
    request then fails.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def hit(self, key: str, *, limit: int, window: timedelta) -> None:
        """Count an attempt under `key`; raise RateLimitedError past `limit`."""

        now = datetime.now(UTC)
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        window_start = epoch + (now - epoch) // window * window

        hits = await self._db.scalar(
            insert(RateLimitCounter)
            .values(key=key, window_start=window_start, hits=1)
            .on_conflict_do_update(
                index_elements=[RateLimitCounter.key, RateLimitCounter.window_start],
                set_={"hits": RateLimitCounter.hits + 1},
            )
            .returning(RateLimitCounter.hits)
        )

        if hits is not None and hits > limit:
            raise RateLimitedError(window_start + window - now)
