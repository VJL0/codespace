from fastapi import HTTPException, Request, status

from app.core.config import settings


async def require_same_origin(request: Request) -> None:
    """Refuse state-changing requests that didn't come from the app itself.

    Fetch Metadata says where a browser request came from; browsers without
    it send Origin instead (OWASP's required fallback). Either must name
    this origin: a cross-site page, or a same-site sibling, is refused.
    """

    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    fetch_site = request.headers.get("sec-fetch-site")

    if (
        request.headers.get("origin") != settings.app_url
        if fetch_site is None
        else fetch_site != "same-origin"
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request refused.")
