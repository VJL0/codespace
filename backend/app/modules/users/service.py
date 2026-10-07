from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.emails import normalize_email
from app.modules.users.models import UserEmail


async def get_verified_email(db: AsyncSession, address: str) -> UserEmail | None:
    """The verified address matching `address`, whoever's it is; raises
    EmailNotValidError for an invalid one."""

    return await db.scalar(
        select(UserEmail).where(
            UserEmail.normalized_email == normalize_email(address),
            UserEmail.verified_at.is_not(None),
        )
    )


async def get_primary_email(db: AsyncSession, user_id: uuid.UUID) -> UserEmail | None:
    return await db.scalar(
        select(UserEmail).where(UserEmail.user_id == user_id, UserEmail.is_primary)
    )


async def list_emails(db: AsyncSession, user_id: uuid.UUID) -> list[UserEmail]:
    return list(
        await db.scalars(
            select(UserEmail)
            .where(UserEmail.user_id == user_id)
            .order_by(UserEmail.is_primary.desc(), UserEmail.created_at)
        )
    )
