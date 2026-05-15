from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.users import get_user_by_public_id
from app.schemas.common import PublicId
from app.schemas.users import UserRead


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{public_id}", response_model=UserRead)
async def read_user(
    public_id: PublicId,
    session: AsyncSession = Depends(get_db),
) -> UserRead:
    user = await get_user_by_public_id(session, public_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return UserRead.from_user(user)
