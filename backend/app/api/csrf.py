from fastapi import HTTPException, Request, status

from app.core.config import settings


async def require_same_origin(request: Request) -> None:
    """Refuse state-changing requests that didn't come from the app itself.

    The SPA and API share one origin, and the API sends no CORS headers, so
    a cross-origin page can't send the custom header without a preflight the
    browser then fails. Fetch Metadata, or Origin on browsers without it,
    rejects what the header alone wouldn't: a same-site sibling, for one.
    """

    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    fetch_site = request.headers.get("sec-fetch-site")

    if request.headers.get("x-csrf-protection") != "1" or (
        request.headers.get("origin") != settings.app_url
        if fetch_site is None
        else fetch_site != "same-origin"
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request refused.")
