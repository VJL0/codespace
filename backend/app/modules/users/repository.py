from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, UserEmail


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._db.get(User, user_id)

    def add(self, user: User) -> None:
        self._db.add(user)


class UserEmailRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_verified(self, normalized_email: str) -> UserEmail | None:
        """The verified address with this normalize_email() key, whoever's it is."""

        return await self._db.scalar(
            select(UserEmail).where(
                UserEmail.normalized_email == normalized_email,
                UserEmail.verified_at.is_not(None),
            )
        )

    async def get_primary(self, user_id: uuid.UUID) -> UserEmail | None:
        return await self._db.scalar(
            select(UserEmail).where(
                UserEmail.user_id == user_id, UserEmail.is_primary.is_(True)
            )
        )

    def add(self, email: UserEmail) -> None:
        self._db.add(email)
