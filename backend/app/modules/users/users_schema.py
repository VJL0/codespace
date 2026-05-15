# app/schemas/user.py

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


def normalize_email(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    return value.strip().lower()


def normalize_optional_string(value: Any) -> Any:
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    value = value.strip()

    return value or None


PublicId = Annotated[
    str,
    StringConstraints(
        min_length=12,
        max_length=12,
        pattern=r"^[A-Za-z0-9]{12}$",
    ),
]

NormalizedEmail = Annotated[
    EmailStr,
    BeforeValidator(normalize_email),
    Field(max_length=254),
]

OptionalUserName = Annotated[
    str | None,
    BeforeValidator(normalize_optional_string),
    Field(min_length=1, max_length=200),
]

Password = Annotated[
    str,
    StringConstraints(
        min_length=8,
        max_length=128,
    ),
]

PasswordHash = Annotated[
    str,
    StringConstraints(
        min_length=20,
        max_length=255,
    ),
]


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ORMBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(StrictBaseModel):
    email: NormalizedEmail
    name: OptionalUserName = None
    password: Password


class UserCreateInternal(StrictBaseModel):
    email: NormalizedEmail
    name: OptionalUserName = None
    password_hash: PasswordHash | None = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    is_verified: bool = False


class UserUpdate(StrictBaseModel):
    name: OptionalUserName = None


class UserAdminUpdate(StrictBaseModel):
    email: NormalizedEmail | None = None
    name: OptionalUserName = None
    role: UserRole | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


class UserPasswordChange(StrictBaseModel):
    current_password: Password
    new_password: Password


class UserRead(ORMBaseModel):
    public_id: PublicId
    email: EmailStr
    name: str | None
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class UserAdminRead(UserRead):
    last_login_at: datetime | None


class UserListResponse(ORMBaseModel):
    items: list[UserAdminRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
