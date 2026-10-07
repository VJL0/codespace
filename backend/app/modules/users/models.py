from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base
from app.models.mixins import TimestampMixin
from app.modules.users.emails import normalize_email


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)

    full_name: Mapped[str | None] = mapped_column(Text)

    avatar_url: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(server_default=text("true"))

    last_sign_in_at: Mapped[datetime | None]

    def __repr__(self) -> str:
        return f"User(id={self.id!s})"


class UserEmail(TimestampMixin, Base):
    """An email address of a user's (User 1 ─── * UserEmail).

    A verified address belongs to one user only; an unverified one is just a
    claim, which never blocks the real owner from verifying it.
    """

    __tablename__ = "user_emails"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    email: Mapped[str] = mapped_column(String(254))

    # normalize_email(email), set with it: what lookups and uniqueness use.
    normalized_email: Mapped[str] = mapped_column(String(254))

    verified_at: Mapped[datetime | None]

    is_primary: Mapped[bool] = mapped_column(server_default=text("false"))

    user: Mapped[User] = relationship(lazy="raise")

    __table_args__ = (
        UniqueConstraint("user_id", "normalized_email"),
        Index(
            "uq_user_emails_normalized_email_verified",
            "normalized_email",
            unique=True,
            postgresql_where=text("verified_at IS NOT NULL"),
        ),
        Index(
            "uq_user_emails_user_id_primary",
            "user_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        CheckConstraint(
            "NOT is_primary OR verified_at IS NOT NULL", name="primary_is_verified"
        ),
    )

    @validates("email")
    def set_normalized_email(self, key: str, value: str) -> str:
        self.normalized_email = normalize_email(value)

        return value.strip()

    def __repr__(self) -> str:
        return f"UserEmail(id={self.id!s}, user_id={self.user_id!s})"
