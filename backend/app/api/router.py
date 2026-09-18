from fastapi import APIRouter

from app.modules.auth.oauth.google import router as google_oauth_router
from app.modules.auth.router import router as auth_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(google_oauth_router, prefix="/auth/google", tags=["auth"])
