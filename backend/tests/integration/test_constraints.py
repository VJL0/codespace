"""Rules the database enforces itself: who may own a verified email."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import UserEmail
from tests.support.database import MakeUser, assert_rejected


async def test_a_verified_email_belongs_to_one_user(
    db: AsyncSession, make_user: MakeUser
) -> None:
    await make_user(email="Ada@Example.COM")
    other = await make_user(email=None)

    await assert_rejected(
        db,
        "uq_user_emails_normalized_email_verified",
        "INSERT INTO user_emails (id, user_id, email, normalized_email, verified_at)"
        " VALUES (:id, :user_id, 'Ada@example.com', 'Ada@example.com', now())",
        id=str(uuid.uuid7()),
        user_id=str(other.id),
    )


async def test_an_unverified_claim_never_blocks_the_owner(
    db: AsyncSession, make_user: MakeUser
) -> None:
    claimant = await make_user(email=None)
    db.add(UserEmail(user=claimant, email="grace@example.com"))
    await db.flush()

    await make_user(email="grace@example.com")


async def test_a_user_has_one_primary_email(
    db: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user(email="ada@example.com")

    await assert_rejected(
        db,
        "uq_user_emails_user_id_primary",
        "INSERT INTO user_emails"
        " (id, user_id, email, normalized_email, verified_at, is_primary)"
        " VALUES (:id, :user_id, 'b@example.com', 'b@example.com', now(), true)",
        id=str(uuid.uuid7()),
        user_id=str(user.id),
    )
