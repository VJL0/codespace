from fastapi import APIRouter, Depends

from app.api.csrf import require_same_origin
from app.modules.auth.router import router as auth_router

api_router = APIRouter(dependencies=[Depends(require_same_origin)])

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
