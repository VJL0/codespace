from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    UserAdminUpdate,
    UserCreate,
    UserCreateInternal,
    UserListResponse,
    UserUpdate,
)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def get_user_by_public_id(self, public_id: UUID) -> User:
        user = await self.users.get_by_public_id(public_id)

        if user is None:
            raise NotFoundError("User not found.")

        return user

    async def create_user(self, payload: UserCreate) -> User:
        existing_user = await self.users.get_by_email(str(payload.email))

        if existing_user is not None:
            raise ConflictError("A user with this email already exists.")

        internal_payload = UserCreateInternal(
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            password_hash=hash_password(payload.password),
            is_active=True,
            is_verified=False,
            is_superuser=False,
        )

        try:
            user = await self.users.create(internal_payload)
            await self.session.commit()

            return user

        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("A user with this email already exists.") from exc
