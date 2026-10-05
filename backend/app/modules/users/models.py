from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)

    # 254: RFC 5321 caps a path at 256 octets including the angle brackets.
    email: Mapped[str] = mapped_column(String(254), unique=True)

    full_name: Mapped[str | None] = mapped_column(Text)

    avatar_url: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(server_default=text("true"))

    last_sign_in_at: Mapped[datetime | None]

    __table_args__ = (CheckConstraint("length(email) > 0", name="email_not_empty"),)

    @validates("email")
    def normalize_email(self, key: str, value: str) -> str:
        email = value.strip().lower()

        if not email:
            raise ValueError("Email cannot be empty.")

        return email

    def __repr__(self) -> str:
        return f"User(id={self.id!s}, email={self.email!r})"
