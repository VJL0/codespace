"""Test database lifecycle and query helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.base import Base
from app.modules.users.models import User
from tests.support.environment import BACKEND_DIR

type MakeUser = Callable[..., Awaitable[User]]
"""The `make_user` fixture: `await make_user(email=... | None, **fields)`."""


def alembic_config() -> Config:
    # pyproject.toml only: alembic.ini holds just logging config, and its
    # fileConfig() would replace the root log handlers pytest captures with.
    return Config(toml_file=BACKEND_DIR / "pyproject.toml")


async def _execute(url: str, *statements: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)

    async with engine.connect() as connection:
        for statement in statements:
            await connection.execute(text(statement))

    await engine.dispose()


def migrate_fresh_schema() -> None:
    """Drop everything in the test database and migrate it back to head."""

    asyncio.run(
        _execute(
            settings.database_url, "DROP SCHEMA public CASCADE", "CREATE SCHEMA public"
        )
    )
    command.upgrade(alembic_config(), "head")


def query(statement: str) -> list[tuple]:
    """Run a read on its own connection, outside any test's transaction."""

    async def run() -> list[tuple]:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)

        async with engine.connect() as connection:
            rows = (await connection.execute(text(statement))).all()

        await engine.dispose()

        return [tuple(row) for row in rows]

    return asyncio.run(run())


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
