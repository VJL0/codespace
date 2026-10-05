"""EmailTokenRepository against the database: single use, expiry, binding."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import EmailToken, EmailTokenPurpose, UserSession
from app.modules.auth.repository import UserSessionRepository
from app.modules.auth.session import SessionService
from app.modules.auth.tokens import EmailTokenRepository
from app.modules.users.models import User
from tests.support.database import MakeUser

SIGNUP = EmailTokenPurpose.SIGNUP
REAUTHENTICATION = EmailTokenPurpose.REAUTHENTICATION


@pytest.fixture
def tokens(db: AsyncSession) -> EmailTokenRepository:
    return EmailTokenRepository(db)


async def issue(
    db: AsyncSession,
    tokens: EmailTokenRepository,
    *,
    purpose: EmailTokenPurpose = SIGNUP,
    lifetime: timedelta = timedelta(hours=1),
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> str:
    _, secret = tokens.issue(
        purpose,
        email="ada@example.com",
        lifetime=lifetime,
        user_id=user_id,
        session_id=session_id,
    )
    await db.flush()

    return secret


async def test_a_token_works_once(
    db: AsyncSession, tokens: EmailTokenRepository
) -> None:
    secret = await issue(db, tokens)

    first = await tokens.consume(SIGNUP, secret)
    second = await tokens.consume(SIGNUP, secret)

    assert first is not None
    assert first.email == "ada@example.com"
    assert first.consumed_at is not None
    assert second is None


async def test_only_a_hash_of_the_secret_is_stored(
    db: AsyncSession, tokens: EmailTokenRepository
) -> None:
    secret = await issue(db, tokens)

    rows = str((await db.execute(text("SELECT * FROM email_tokens"))).all())

    assert secret not in rows


async def test_an_expired_token_doesnt_work(
    db: AsyncSession, tokens: EmailTokenRepository
) -> None:
    secret = await issue(db, tokens, lifetime=timedelta(seconds=-1))

    assert await tokens.consume(SIGNUP, secret) is None


async def test_a_token_works_only_for_its_purpose(
    db: AsyncSession, tokens: EmailTokenRepository
) -> None:
    secret = await issue(db, tokens)

    assert await tokens.consume(EmailTokenPurpose.PASSWORD_RESET, secret) is None
    assert await tokens.consume(SIGNUP, secret) is not None


async def test_an_unknown_secret_matches_nothing(tokens: EmailTokenRepository) -> None:
    assert await tokens.consume(SIGNUP, "not-a-secret") is None


async def session_of(db: AsyncSession, user: User) -> UserSession:
    SessionService(UserSessionRepository(db)).create_session(user=user, fresh=False)
    await db.flush()
    user_session = await db.scalar(
        select(UserSession).where(UserSession.user_id == user.id)
    )
    assert user_session is not None

    return user_session


async def test_a_session_bound_token_is_left_unspent_by_other_sessions(
    db: AsyncSession, tokens: EmailTokenRepository, make_user: MakeUser
) -> None:
    user = await make_user()
    mine = await session_of(db, user)
    other = await session_of(db, await make_user(email=None))
    secret = await issue(
        db, tokens, purpose=REAUTHENTICATION, user_id=user.id, session_id=mine.id
    )

    assert await tokens.consume(REAUTHENTICATION, secret, session_id=other.id) is None
    assert await tokens.consume(REAUTHENTICATION, secret, session_id=mine.id)


async def test_revoking_spends_a_users_unused_tokens(
    db: AsyncSession, tokens: EmailTokenRepository, make_user: MakeUser
) -> None:
    user = await make_user()
    reset = EmailTokenPurpose.PASSWORD_RESET
    old = await issue(db, tokens, purpose=reset, user_id=user.id)
    other_purpose = await issue(db, tokens, purpose=REAUTHENTICATION, user_id=user.id)

    await tokens.revoke(reset, user.id)

    assert await tokens.consume(reset, old) is None
    assert await tokens.consume(REAUTHENTICATION, other_purpose) is not None
    assert await db.scalar(select(EmailToken).where(EmailToken.purpose == reset))
