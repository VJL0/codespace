"""Scheduled jobs. Vercel Cron calls them (see vercel.json) with a GET and
`Authorization: Bearer $CRON_SECRET`; they must be safe to run twice, as
its delivery may repeat a run or skip one."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.deps import SessionDep
from app.core.config import settings
from app.modules.auth import service as auth_service


async def require_cron_secret(
    authorization: Annotated[str, Header()] = "",
) -> None:
    # An unset secret refuses every call, rather than matching "Bearer ".
    if not settings.cron_secret or not secrets.compare_digest(
        authorization.encode(), f"Bearer {settings.cron_secret}".encode()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")


router = APIRouter(dependencies=[Depends(require_cron_secret)])


@router.get("/purge-expired", status_code=204)
async def purge_expired(db: SessionDep) -> None:
    await auth_service.purge_expired(db)
    await db.commit()
