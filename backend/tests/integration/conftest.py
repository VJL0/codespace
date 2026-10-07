"""Fixtures for tests against PostgreSQL.

Each run starts its own PostgreSQL container (Testcontainers; Docker must be
running), migrates it once, and removes it at the end. Each test runs inside
a transaction that is rolled back afterwards, so tests see only their own
writes, commits included.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from app.core.config import settings
from app.modules.users.models import User, UserEmail
from tests.support.database import MakeUser, alembic_config


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[str]:
    """A migrated database for the run; yields its URL, which the app's
    settings (and so Alembic and the lifespan) point at meanwhile."""

    # The image compose.yml runs, so tests see the same PostgreSQL. Its data
    # is thrown away, so it runs in RAM without durability, as PostgreSQL's
    # "Non-Durable Settings" recommend.
    postgres = (
        PostgresContainer("postgres:18-alpine", driver="asyncpg")
        .with_command(
            "postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off"
        )
        .with_tmpfs_mount("/var/lib/postgresql")
    )

    with postgres, pytest.MonkeyPatch.context() as patch:
        url = postgres.get_connection_url()
        patch.setattr(settings, "database_url", url)
        command.upgrade(alembic_config(), "head")

        yield url


@pytest.fixture(scope="session")
def engine(database: str) -> AsyncEngine:
    # No pool: each test runs on its own event loop, and pooled asyncpg
    # connections can't move between loops.
    return create_async_engine(database, poolclass=NullPool)


@pytest.fixture
async def connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


@pytest.fixture
def session_factory(connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    # "create_savepoint" turns the app's commits into savepoint releases, so
    # the rollback in `connection` still undoes everything.
    return async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
async def db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def make_user(db: AsyncSession) -> MakeUser:
    """Insert a user, flushed so it has an id: `await make_user(email=...)`.

    `email` becomes their verified primary address; None gives them none.
    """

    async def make(email: str | None = "ada@example.com", **fields: Any) -> User:
        user = User(**fields)
        db.add(user)

        if email is not None:
            db.add(
                UserEmail(
                    user=user,
                    email=email,
                    verified_at=datetime.now(UTC),
                    is_primary=True,
                )
            )

        await db.flush()

        return user

    return make
