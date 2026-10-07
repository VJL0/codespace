from fastapi import APIRouter, Depends

from app.api.cron import router as cron_router
from app.api.csrf import require_same_origin
from app.modules.auth.password_router import router as password_router
from app.modules.auth.router import router as auth_router

api_router = APIRouter(dependencies=[Depends(require_same_origin)])

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(password_router, prefix="/auth", tags=["auth"])
api_router.include_router(cron_router, prefix="/cron", include_in_schema=False)
