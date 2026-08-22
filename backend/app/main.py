from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.database import check_database, engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    debug=settings.is_development,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
    lifespan=lifespan,
)


app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,
    www_redirect=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health/live", include_in_schema=False)
async def liveness_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def readiness_check() -> dict[str, str]:
    await check_database()
    return {"status": "ok"}
