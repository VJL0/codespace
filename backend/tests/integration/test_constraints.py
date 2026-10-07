"""Database-level rules: the constraints the migration creates, not ORM checks."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OAuthAccount, OAuthProvider
from app.modules.users.models import User
from tests.support.database import MakeUser, assert_rejected


@pytest.fixture
async def user(db: AsyncSession, make_user: MakeUser) -> User:
    """A user with a Google account."""

    user = await make_user(email="  Ada@Example.COM ")
    db.add(
        OAuthAccount(user=user, provider=OAuthProvider.GOOGLE, provider_user_id="g-1")
    )
    await db.flush()

    return user


def new_id() -> str:
    return str(uuid.uuid7())


async def test_server_defaults_are_applied(db: AsyncSession, user: User) -> None:
    await db.refresh(user)

    assert user.is_active is True
    assert isinstance(user.created_at, datetime)
    assert user.created_at.tzinfo is not None


async def test_provider_is_stored_as_its_lowercase_value(
    db: AsyncSession, user: User
) -> None:
    assert (
        await db.scalar(text("SELECT provider::text FROM oauth_accounts")) == "google"
    )


async def test_empty_provider_user_id_is_rejected(db: AsyncSession, user: User) -> None:
    await assert_rejected(
        db,
        "ck_oauth_accounts_provider_user_id_not_empty",
        "UPDATE oauth_accounts SET provider_user_id = ''",
    )


async def test_empty_email_is_rejected(db: AsyncSession) -> None:
    await assert_rejected(
        db,
        "ck_users_email_not_empty",
        "INSERT INTO users (id, email) VALUES (:id, '')",
        id=new_id(),
    )


async def test_session_cannot_expire_before_it_starts(
    db: AsyncSession, user: User
) -> None:
    await assert_rejected(
        db,
        "ck_user_sessions_expires_after_created",
        "INSERT INTO user_sessions (id, user_id, token_hash, expires_at)"
        " VALUES (:id, :user_id, 'hash', now() - interval '1 second')",
        id=new_id(),
        user_id=str(user.id),
    )
