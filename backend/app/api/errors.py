from fastapi import HTTPException


def api_error(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    """An error the SPA can act on: `{"detail": {"code": ..., "message": ...}}`."""

    return HTTPException(status_code, {"code": code, "message": message}, headers)
