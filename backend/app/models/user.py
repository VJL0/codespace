# app/models/user.py

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.public_ids import generate_public_id
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.models.classroom import ClassroomMember


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class OAuthProvider(str, enum.Enum):
    GOOGLE = "google"


class User(TimestampMixin, Base):
    """
    Application user account.

    This table stores identity/account data only.

    Internal database relationships should use `id`.

    Public routes and API responses should use `public_id`.

    Classroom permissions such as owner, teacher, co-teacher, and student
    belong in ClassroomMember, not directly on User.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    public_id: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default=generate_public_id,
    )

    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
    )

    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    avatar_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=text("'user'"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    oauth_accounts: Mapped[list[UserOAuthAccount]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    classroom_memberships: Mapped[list[ClassroomMember]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "email",
            name="uq_users_email",
        ),
        UniqueConstraint(
            "public_id",
            name="uq_users_public_id",
        ),
        CheckConstraint(
            "length(email) > 0",
            name="ck_users_email_not_empty",
        ),
        CheckConstraint(
            "length(public_id) = 12",
            name="ck_users_public_id_length",
        ),
        CheckConstraint(
            "public_id ~ '^[A-Za-z0-9]{12}$'",
            name="ck_users_public_id_format",
        ),
        CheckConstraint(
            "password_hash IS NULL OR length(password_hash) >= 20",
            name="ck_users_password_hash_length",
        ),
        Index("ix_users_is_active", "is_active"),
    )

    @validates("email")
    def normalize_email(self, key: str, value: str) -> str:
        email = value.strip().lower()

        if not email:
            raise ValueError("Email cannot be empty.")

        return email

    @validates("public_id")
    def validate_public_id(self, key: str, value: str) -> str:
        public_id = value.strip()

        if len(public_id) != 12:
            raise ValueError("Public ID must be exactly 12 characters.")

        if not public_id.isalnum():
            raise ValueError("Public ID must contain only letters and numbers.")

        return public_id

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def has_oauth(self) -> bool:
        return bool(self.oauth_accounts)

    @property
    def auth_methods(self) -> Sequence[str]:
        methods: list[str] = []

        if self.has_password:
            methods.append("password")

        methods.extend(account.provider.value for account in self.oauth_accounts)

        return methods

    def __repr__(self) -> str:
        return (
            "User("
            f"id={self.id!s}, "
            f"public_id={self.public_id!r}, "
            f"email={self.email!r}, "
            f"role={self.role.value!r}"
            ")"
        )


class UserOAuthAccount(TimestampMixin, Base):
    """
    External OAuth identity linked to a user.

    For Google, provider_user_id should store the stable OIDC `sub` claim,
    not the Google email address.
    """

    __tablename__ = "user_oauth_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider: Mapped[OAuthProvider] = mapped_column(
        Enum(
            OAuthProvider,
            name="oauth_provider",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    provider_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    provider_email: Mapped[str | None] = mapped_column(
        String(254),
        nullable=True,
    )

    provider_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped[User] = relationship(
        back_populates="oauth_accounts",
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_user_oauth_accounts_provider_provider_user_id",
        ),
        UniqueConstraint(
            "user_id",
            "provider",
            name="uq_user_oauth_accounts_user_id_provider",
        ),
        CheckConstraint(
            "length(provider_user_id) > 0",
            name="provider_user_id_not_empty",
        ),
        Index("ix_user_oauth_accounts_user_id", "user_id"),
        Index("ix_user_oauth_accounts_provider_email", "provider_email"),
    )

    @validates("provider_email")
    def normalize_provider_email(self, key: str, value: str | None) -> str | None:
        if value is None:
            return None

        email = value.strip().lower()

        return email or None

    def __repr__(self) -> str:
        return (
            "UserOAuthAccount("
            f"id={self.id!s}, "
            f"user_id={self.user_id!s}, "
            f"provider={self.provider.value!r}"
            ")"
        )
