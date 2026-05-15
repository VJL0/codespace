from fastapi import APIRouter

from app.api.deps import DbSession
from app.modules.auth.dependencies import CurrentUser


router = APIRouter()


@router.get("/me")
async def get_me(current_user: CurrentUser):
    return current_user


@router.get("/{user_id}")
async def get_user(user_id: str, db: DbSession): ...
