from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.lifespan import get_app_state


async def get_engine(request: Request) -> AsyncEngine:
    return get_app_state(request)["engine"]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with get_app_state(request)["session_factory"]() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
