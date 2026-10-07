"""Test database helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base
from app.modules.users.models import User
from tests.support.environment import BACKEND_DIR

type MakeUser = Callable[..., Awaitable[User]]
"""The `make_user` fixture: `await make_user(email=... | None, **fields)`."""


def alembic_config() -> Config:
    # pyproject.toml only: alembic.ini holds just logging config, and its
    # fileConfig() would replace the root log handlers pytest captures with.
    return Config(toml_file=BACKEND_DIR / "pyproject.toml")


async def count_rows(db: AsyncSession, model: type[Base]) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


async def assert_rejected(
    db: AsyncSession, constraint: str, statement: str, **params: object
) -> None:
    """Run raw SQL that must violate `constraint`, inside a savepoint so the
    test's transaction stays usable."""

    with pytest.raises(DBAPIError) as caught:
        async with db.begin_nested():
            await db.execute(text(statement), params)

    assert constraint in str(caught.value.orig)
