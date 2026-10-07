"""SessionService against the database: lifetimes, revocation and storage."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import UserSession
from app.modules.auth.repository import UserSessionRepository
from app.modules.auth.session import SessionService
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from tests.support.database import MakeUser, count_rows


@pytest.fixture
def sessions(db: AsyncSession) -> SessionService:
    return SessionService(UserSessionRepository(db), UserRepository(db))


@pytest.fixture
async def user(make_user: MakeUser) -> User:
    return await make_user()


async def start_session(db: AsyncSession, sessions: SessionService, user: User) -> str:
    token = sessions.create_session(user=user)
    await db.commit()

    return token


async def set_session_times(db: AsyncSession, **times: datetime) -> None:
    await db.execute(update(UserSession).values(**times))
    db.expunge_all()


async def test_token_resolves_to_its_user(
    db: AsyncSession, sessions: SessionService, user: User
) -> None:
    token = await start_session(db, sessions, user)

    resolved = await sessions.get_user_for_session(token)

    assert resolved is not None
    assert resolved.id == user.id


async def test_only_a_hash_of_the_token_is_stored(
    db: AsyncSession, sessions: SessionService, user: User
) -> None:
    token = await start_session(db, sessions, user)

    stored = await db.scalar(select(UserSession.token_hash))

    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(
        (await db.execute(text("SELECT * FROM user_sessions"))).all()
    )


async def test_idle_session_is_rejected_and_deleted(
    db: AsyncSession, sessions: SessionService, user: User
) -> None:
    token = await start_session(db, sessions, user)
    await set_session_times(db, last_seen_at=datetime.now(UTC) - timedelta(minutes=30))

    assert await sessions.get_user_for_session(token) is None
    assert await count_rows(db, UserSession) == 0


async def test_session_past_absolute_expiry_is_rejected_and_deleted(
    db: AsyncSession, sessions: SessionService, user: User
) -> None:
    token = await start_session(db, sessions, user)
    now = datetime.now(UTC)
    await set_session_times(
        db,
        created_at=now - timedelta(days=15),
        expires_at=now - timedelta(seconds=1),
        last_seen_at=now,
    )

    assert await sessions.get_user_for_session(token) is None
    assert await count_rows(db, UserSession) == 0


async def test_activity_refreshes_last_seen_at_at_most_once_a_minute(
    db: AsyncSession, sessions: SessionService, user: User
) -> None:
    token = await start_session(db, sessions, user)
    recent = datetime.now(UTC) - timedelta(seconds=30)
    await set_session_times(db, last_seen_at=recent)

    await sessions.get_user_for_session(token)
    await db.flush()
    assert await db.scalar(select(UserSession.last_seen_at)) == recent

    stale = datetime.now(UTC) - timedelta(minutes=5)
    await set_session_times(db, last_seen_at=stale)

    await sessions.get_user_for_session(token)
    await db.flush()
    refreshed = await db.scalar(select(UserSession.last_seen_at))
    assert refreshed is not None
    assert refreshed > stale


async def test_inactive_user_is_rejected(
    db: AsyncSession, sessions: SessionService, user: User
) -> None:
    token = await start_session(db, sessions, user)
    user.is_active = False
    await db.flush()

    assert await sessions.get_user_for_session(token) is None


async def test_revoked_session_no_longer_resolves(
    db: AsyncSession, sessions: SessionService, user: User
) -> None:
    token = await start_session(db, sessions, user)

    await sessions.revoke_session(token)

    assert await sessions.get_user_for_session(token) is None
    assert await count_rows(db, UserSession) == 0


async def test_unknown_token_resolves_to_nobody(sessions: SessionService) -> None:
    assert await sessions.get_user_for_session("not-a-real-token") is None
