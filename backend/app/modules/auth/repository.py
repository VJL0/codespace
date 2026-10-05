from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.auth.models import (
    OAuthAccount,
    OAuthProvider,
    PasswordCredential,
    UserSession,
)


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

    async def get_for_user(
        self, user_id: uuid.UUID, provider: OAuthProvider
    ) -> OAuthAccount | None:
        return await self._db.scalar(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user_id, OAuthAccount.provider == provider
            )
        )

    async def list_for_user(self, user_id: uuid.UUID) -> list[OAuthAccount]:
        return list(
            await self._db.scalars(
                select(OAuthAccount)
                .where(OAuthAccount.user_id == user_id)
                .order_by(OAuthAccount.created_at)
            )
        )

    def add(self, account: OAuthAccount) -> None:
        self._db.add(account)

    async def delete(self, account: OAuthAccount) -> None:
        await self._db.delete(account)


class UserSessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        """The session with this token hash, its user loaded."""

        return await self._db.scalar(
            select(UserSession)
            .options(joinedload(UserSession.user))
            .where(UserSession.token_hash == token_hash)
        )

    def add(self, user_session: UserSession) -> None:
        self._db.add(user_session)

    async def delete(self, user_session: UserSession) -> None:
        await self._db.delete(user_session)

    async def delete_by_token_hash(self, token_hash: str) -> None:
        await self._db.execute(
            delete(UserSession).where(UserSession.token_hash == token_hash)
        )

    async def delete_for_user(
        self, user_id: uuid.UUID, *, keep: uuid.UUID | None = None
    ) -> None:
        """Delete the user's sessions, all of them or all but `keep`."""

        statement = delete(UserSession).where(UserSession.user_id == user_id)

        if keep is not None:
            statement = statement.where(UserSession.id != keep)

        await self._db.execute(statement)


class PasswordCredentialRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID) -> PasswordCredential | None:
        return await self._db.get(PasswordCredential, user_id)

    def add(self, credential: PasswordCredential) -> None:
        self._db.add(credential)

    async def delete(self, credential: PasswordCredential) -> None:
        await self._db.delete(credential)
