from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime, timedelta

from fastapi import Request, status
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import api_error
from app.core.config import settings
from app.modules.auth.models import RateLimitCounter
from app.modules.users.emails import EmailNotValidError, normalize_email

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


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


async def rate_limit(db: AsyncSession, *buckets: tuple[str, int, timedelta]) -> None:
    """Count this attempt in each (key, limit, window) bucket; refuse with 429
    once one is full.

    Fixed windows in PostgreSQL, shared by every app worker. Committed here,
    so failed attempts count even when the request then fails. Nothing is
    locked: the window simply passes.
    """

    now = datetime.now(UTC)
    retry_after = None

    for key, limit, window in buckets:
        window_start = _EPOCH + (now - _EPOCH) // window * window
        hits = (
            await db.execute(
                insert(RateLimitCounter)
                .values(key=key, window_start=window_start, hits=1)
                .on_conflict_do_update(
                    index_elements=[
                        RateLimitCounter.key,
                        RateLimitCounter.window_start,
                    ],
                    set_={"hits": RateLimitCounter.hits + 1},
                )
                .returning(RateLimitCounter.hits)
            )
        ).scalar_one()

        if hits > limit:
            retry_after = window_start + window - now
            break

    await db.commit()

    if retry_after is not None:
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "Too many attempts. Wait a while and try again.",
            headers={"Retry-After": str(int(retry_after.total_seconds()) + 1)},
        )
