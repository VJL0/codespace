# app/models/classroom.py

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

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ClassroomRole(str, enum.Enum):
    OWNER = "owner"
    TEACHER = "teacher"
    CO_TEACHER = "co_teacher"
    STUDENT = "student"


class Classroom(TimestampMixin, Base):
    """
    Classroom created by a teacher.

    A classroom can contain real authenticated users and anonymous classroom
    seats. The class code belongs to the classroom, not to an individual seat.
    """

    __tablename__ = "classrooms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    public_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    class_code_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    safe_mode_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    student_sharing_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    members: Mapped[list[ClassroomMember]] = relationship(
        back_populates="classroom",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    seats: Mapped[list[ClassroomSeat]] = relationship(
        back_populates="classroom",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "public_id",
            name="uq_classrooms_public_id",
        ),
        UniqueConstraint(
            "class_code_hash",
            name="uq_classrooms_class_code_hash",
        ),
        CheckConstraint(
            "length(public_id) > 0",
            name="classroom_public_id_not_empty",
        ),
        CheckConstraint(
            "length(name) > 0",
            name="classroom_name_not_empty",
        ),
        CheckConstraint(
            "length(class_code_hash) >= 20",
            name="classroom_class_code_hash_valid",
        ),
        Index("ix_classrooms_public_id", "public_id"),
        Index("ix_classrooms_is_active", "is_active"),
    )

    @validates("name")
    def normalize_name(self, key: str, value: str) -> str:
        name = value.strip()

        if not name:
            raise ValueError("Classroom name cannot be empty.")

        return name

    def __repr__(self) -> str:
        return f"Classroom(id={self.id!s}, name={self.name!r})"


class ClassroomSeat(TimestampMixin, Base):
    """
    Anonymous classroom-local student identity.

    A seat is not a real authenticated user account. It belongs to exactly one
    classroom and is identified inside that classroom by a nickname.

    Seats can later be claimed/graduated into a full User account.
    """

    __tablename__ = "classroom_seats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    public_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )

    classroom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classrooms.id", ondelete="CASCADE"),
        nullable=False,
    )

    nickname: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    normalized_nickname: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    seat_code_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    claimed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    classroom: Mapped[Classroom] = relationship(
        back_populates="seats",
    )

    claimed_by_user: Mapped[User | None] = relationship(
        foreign_keys=[claimed_by_user_id],
    )

    member: Mapped[ClassroomMember | None] = relationship(
        back_populates="seat",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "public_id",
            name="uq_classroom_seats_public_id",
        ),
        UniqueConstraint(
            "classroom_id",
            "normalized_nickname",
            name="uq_classroom_seats_classroom_id_normalized_nickname",
        ),
        CheckConstraint(
            "length(public_id) > 0",
            name="classroom_seat_public_id_not_empty",
        ),
        CheckConstraint(
            "length(nickname) > 0",
            name="classroom_seat_nickname_not_empty",
        ),
        CheckConstraint(
            "length(normalized_nickname) > 0",
            name="classroom_seat_normalized_nickname_not_empty",
        ),
        CheckConstraint(
            "seat_code_hash IS NULL OR length(seat_code_hash) >= 20",
            name="classroom_seat_code_hash_valid",
        ),
        CheckConstraint(
            "(claimed_by_user_id IS NULL AND claimed_at IS NULL) OR "
            "(claimed_by_user_id IS NOT NULL AND claimed_at IS NOT NULL)",
            name="classroom_seat_claim_consistent",
        ),
        Index("ix_classroom_seats_public_id", "public_id"),
        Index("ix_classroom_seats_classroom_id", "classroom_id"),
        Index("ix_classroom_seats_claimed_by_user_id", "claimed_by_user_id"),
        Index("ix_classroom_seats_last_used_at", "last_used_at"),
    )

    @validates("nickname")
    def normalize_nickname(self, key: str, value: str) -> str:
        nickname = " ".join(value.strip().split())

        if not nickname:
            raise ValueError("Seat nickname cannot be empty.")

        self.normalized_nickname = nickname.lower()

        return nickname

    def __repr__(self) -> str:
        return (
            "ClassroomSeat("
            f"id={self.id!s}, "
            f"classroom_id={self.classroom_id!s}, "
            f"nickname={self.nickname!r}"
            ")"
        )


class ClassroomMember(TimestampMixin, Base):
    """
    Membership record for a classroom.

    A member is either backed by a real User account or by an anonymous
    ClassroomSeat. Exactly one identity must be present.
    """

    __tablename__ = "classroom_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    classroom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classrooms.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    seat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classroom_seats.id", ondelete="CASCADE"),
        nullable=True,
    )

    role: Mapped[ClassroomRole] = mapped_column(
        Enum(
            ClassroomRole,
            name="classroom_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    classroom: Mapped[Classroom] = relationship(
        back_populates="members",
    )

    user: Mapped[User | None] = relationship(
        back_populates="classroom_memberships",
        foreign_keys=[user_id],
    )

    seat: Mapped[ClassroomSeat | None] = relationship(
        back_populates="member",
        foreign_keys=[seat_id],
    )

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND seat_id IS NULL) OR "
            "(user_id IS NULL AND seat_id IS NOT NULL)",
            name="classroom_member_exactly_one_identity",
        ),
        UniqueConstraint(
            "classroom_id",
            "user_id",
            name="uq_classroom_members_classroom_id_user_id",
        ),
        UniqueConstraint(
            "classroom_id",
            "seat_id",
            name="uq_classroom_members_classroom_id_seat_id",
        ),
        Index("ix_classroom_members_classroom_id", "classroom_id"),
        Index("ix_classroom_members_user_id", "user_id"),
        Index("ix_classroom_members_seat_id", "seat_id"),
        Index("ix_classroom_members_role", "role"),
    )

    def __repr__(self) -> str:
        identity = (
            f"user_id={self.user_id!s}"
            if self.user_id is not None
            else f"seat_id={self.seat_id!s}"
        )

        return (
            "ClassroomMember("
            f"id={self.id!s}, "
            f"classroom_id={self.classroom_id!s}, "
            f"{identity}, "
            f"role={self.role.value!r}"
            ")"
        )
