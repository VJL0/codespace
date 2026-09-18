from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Imported for side effects: registers every mapped model on Base's registry
# so SQLAlchemy can resolve cross-module relationships (e.g. User <->
# ClassroomMember) the first time any mapper is used.
# TODO: Find a better way to do this
from app.modules.classrooms import models as _classroom_models  # noqa: F401
from app.modules.users import models as _user_models  # noqa: F401

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
