from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserAdminUpdate, UserCreateInternal, UserUpdate


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        statement = select(User).where(User.id == user_id)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_public_id(self, public_id: str) -> User | None:
        statement = select(User).where(User.public_id == public_id)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        normalized_email = self._normalize_email(email)

        statement = select(User).where(User.email == normalized_email)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def exists_by_email(self, email: str) -> bool:
        normalized_email = self._normalize_email(email)

        statement = select(exists().where(User.email == normalized_email))

        result = await self.session.execute(statement)

        return result.scalar_one()

    async def create(self, payload: UserCreateInternal) -> User:

        user = User(
            email=str(payload.email),
            first_name=payload.first_name,
            last_name=payload.last_name,
            password_hash=payload.password_hash,
            is_active=payload.is_active,
            is_verified=payload.is_verified,
            is_superuser=payload.is_superuser,
        )

        self.session.add(user)

        await self.session.flush()
        await self.session.refresh(user)

        return user

    async def update(self, user: User, payload: UserUpdate) -> User:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(user, field, value)

        await self.session.flush()
        await self.session.refresh(user)

        return user

    async def admin_update(self, user: User, payload: UserAdminUpdate) -> User:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(user, field, value)

        await self.session.flush()
        await self.session.refresh(user)

        return user

    async def mark_login_success(self, user: User) -> User:
        user.last_login_at = datetime.now(UTC)

        await self.session.flush()
        await self.session.refresh(user)

        return user

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.flush()

    async def list_users(
        self,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        active_only: bool | None = None,
        verified_only: bool | None = None,
    ) -> list[User]:
        query = select(User).order_by(User.created_at.desc(), User.id.desc())

        query = self._apply_filters(
            query=query,
            search=search,
            active_only=active_only,
            verified_only=verified_only,
        )

        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)

        return list(result.scalars().all())

    async def count_users(
        self,
        *,
        search: str | None = None,
        active_only: bool | None = None,
        verified_only: bool | None = None,
    ) -> int:
        query = select(func.count(User.id))

        query = self._apply_filters(
            query=query,
            search=search,
            active_only=active_only,
            verified_only=verified_only,
        )

        result = await self.session.execute(query)

        return result.scalar_one()

    def _apply_filters(
        self,
        *,
        query: Select,
        search: str | None,
        active_only: bool | None,
        verified_only: bool | None,
    ) -> Select:
        if search:
            normalized_search = f"%{search.strip().lower()}%"

            query = query.where(
                or_(
                    func.lower(User.email).like(normalized_search),
                    func.lower(func.coalesce(User.first_name, "")).like(
                        normalized_search
                    ),
                    func.lower(func.coalesce(User.last_name, "")).like(
                        normalized_search
                    ),
                )
            )

        if active_only is not None:
            query = query.where(User.is_active.is_(active_only))

        if verified_only is not None:
            query = query.where(User.is_verified.is_(verified_only))

        return query

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()
