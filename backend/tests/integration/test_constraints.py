"""Database-level rules: the constraints the migration creates, not ORM checks."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OAuthAccount, OAuthProvider
from app.modules.users.models import User, UserEmail
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


async def test_a_user_has_one_account_per_provider(
    db: AsyncSession, user: User
) -> None:
    await assert_rejected(
        db,
        "uq_oauth_accounts_user_id_provider",
        "INSERT INTO oauth_accounts (id, user_id, provider, provider_user_id)"
        " VALUES (:id, :user_id, 'google', 'g-2')",
        id=new_id(),
        user_id=str(user.id),
    )


async def test_a_user_may_link_several_providers(db: AsyncSession, user: User) -> None:
    db.add(OAuthAccount(user=user, provider=OAuthProvider.GITHUB, provider_user_id="1"))

    await db.flush()


async def test_a_verified_email_belongs_to_one_user(
    db: AsyncSession, user: User, make_user: MakeUser
) -> None:
    other = await make_user(email=None)

    await assert_rejected(
        db,
        "uq_user_emails_normalized_email_verified",
        "INSERT INTO user_emails (id, user_id, email, normalized_email, verified_at)"
        " VALUES (:id, :user_id, 'Ada@example.com', 'Ada@example.com', now())",
        id=new_id(),
        user_id=str(other.id),
    )


async def test_an_unverified_claim_never_blocks_the_owner(
    db: AsyncSession, user: User, make_user: MakeUser
) -> None:
    claimant = await make_user(email=None)
    db.add(UserEmail(user=claimant, email="grace@example.com"))
    await db.flush()

    await make_user(email="grace@example.com")


async def test_a_user_has_one_primary_email(db: AsyncSession, user: User) -> None:
    await assert_rejected(
        db,
        "uq_user_emails_user_id_primary",
        "INSERT INTO user_emails"
        " (id, user_id, email, normalized_email, verified_at, is_primary)"
        " VALUES (:id, :user_id, 'b@example.com', 'b@example.com', now(), true)",
        id=new_id(),
        user_id=str(user.id),
    )


async def test_the_primary_email_is_verified(
    db: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user(email=None)

    await assert_rejected(
        db,
        "ck_user_emails_primary_is_verified",
        "INSERT INTO user_emails (id, user_id, email, normalized_email, is_primary)"
        " VALUES (:id, :user_id, 'b@example.com', 'b@example.com', true)",
        id=new_id(),
        user_id=str(user.id),
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
