"""RateLimiter against the database: fixed windows shared across requests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import RateLimitCounter
from app.modules.auth.rate_limit import RateLimitedError, RateLimiter

WINDOW = timedelta(minutes=15)


@pytest.fixture
def limiter(db: AsyncSession) -> RateLimiter:
    return RateLimiter(db)


async def test_attempts_up_to_the_limit_pass(limiter: RateLimiter) -> None:
    for _ in range(3):
        await limiter.hit("k", limit=3, window=WINDOW)


async def test_the_attempt_past_the_limit_is_refused_until_the_window_ends(
    limiter: RateLimiter,
) -> None:
    for _ in range(3):
        await limiter.hit("k", limit=3, window=WINDOW)

    with pytest.raises(RateLimitedError) as refused:
        await limiter.hit("k", limit=3, window=WINDOW)

    assert timedelta(0) < refused.value.retry_after <= WINDOW


async def test_keys_are_counted_separately(limiter: RateLimiter) -> None:
    await limiter.hit("a", limit=1, window=WINDOW)

    await limiter.hit("b", limit=1, window=WINDOW)


async def test_windows_start_on_multiples_of_their_length(
    db: AsyncSession, limiter: RateLimiter
) -> None:
    await limiter.hit("k", limit=5, window=WINDOW)
    await limiter.hit("k", limit=5, window=WINDOW)

    counter = await db.scalar(select(RateLimitCounter))
    assert counter is not None
    assert counter.hits == 2
    assert counter.window_start.minute % 15 == 0
    assert counter.window_start.second == 0
