from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._db.get(User, user_id)

    async def email_exists(self, email: str) -> bool:
        return bool(await self._db.scalar(select(exists().where(User.email == email))))

    def add(self, user: User) -> None:
        self._db.add(user)
