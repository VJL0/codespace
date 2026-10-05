from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OAuthAccount, OAuthProvider, UserSession


class OAuthAccountRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_provider_user_id(
        self, provider: OAuthProvider, provider_user_id: str
    ) -> OAuthAccount | None:
        return await self._db.scalar(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
        )

    def add(self, account: OAuthAccount) -> None:
        self._db.add(account)


class UserSessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        return await self._db.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash)
        )

    def add(self, user_session: UserSession) -> None:
        self._db.add(user_session)

    async def delete(self, user_session: UserSession) -> None:
        await self._db.delete(user_session)

    async def delete_by_token_hash(self, token_hash: str) -> None:
        await self._db.execute(
            delete(UserSession).where(UserSession.token_hash == token_hash)
        )

    async def delete_for_user(self, user_id: uuid.UUID) -> None:
        await self._db.execute(
            delete(UserSession).where(UserSession.user_id == user_id)
        )
