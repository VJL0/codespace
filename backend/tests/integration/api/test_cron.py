"""Scheduled jobs, as Vercel Cron calls them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import (
    EmailToken,
    EmailTokenPurpose,
    RateLimitCounter,
    UserSession,
)
from tests.support.database import MakeUser

CRON_HEADERS = {"authorization": "Bearer test-cron-secret"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"authorization": "Bearer wrong"}, {"authorization": "test-cron-secret"}],
    ids=["missing", "wrong", "not-bearer"],
)
async def test_a_job_needs_the_cron_secret(
    client: httpx2.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get("/api/cron/purge-expired", headers=headers)

    assert response.status_code == 401


async def test_an_unset_cron_secret_refuses_every_call(
    client: httpx2.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "cron_secret", "")

    response = await client.get(
        "/api/cron/purge-expired", headers={"authorization": "Bearer "}
    )

    assert response.status_code == 401


async def test_purging_deletes_only_what_cant_be_used_again(
    client: httpx2.AsyncClient, db: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    now = datetime.now(UTC)
    later = now + timedelta(hours=1)

    def session(
        name: str, *, expires_at: datetime = later, last_seen_at: datetime = now
    ) -> UserSession:
        return UserSession(
            user_id=user.id,
            token_hash=name.ljust(64, "0"),
            created_at=now - timedelta(days=30),
            expires_at=expires_at,
            last_seen_at=last_seen_at,
        )

    def token(
        name: str, *, expires_at: datetime = later, consumed_at: datetime | None = None
    ) -> EmailToken:
        return EmailToken(
            purpose=EmailTokenPurpose.PASSWORD_RESET,
            email="ada@example.com",
            user_id=user.id,
            token_hash=name.ljust(64, "0"),
            expires_at=expires_at,
            consumed_at=consumed_at,
        )

    db.add_all(
        [
            session("live"),
            session("ended", expires_at=now - timedelta(seconds=1)),
            session("idle", last_seen_at=now - timedelta(hours=1)),
            token("live"),
            token("used", consumed_at=now),
            token("expired", expires_at=now - timedelta(seconds=1)),
            RateLimitCounter(key="current", window_start=now, hits=1),
            RateLimitCounter(key="over", window_start=now - timedelta(days=2), hits=1),
        ]
    )
    await db.flush()

    response = await client.get("/api/cron/purge-expired", headers=CRON_HEADERS)

    assert response.status_code == 204
    db.expire_all()
    assert list(await db.scalars(select(UserSession.token_hash))) == [
        "live".ljust(64, "0")
    ]
    assert list(await db.scalars(select(EmailToken.token_hash))) == [
        "live".ljust(64, "0")
    ]
    assert list(await db.scalars(select(RateLimitCounter.key))) == ["current"]
