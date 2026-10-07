import logging

from app.core.request_id import request_id

logger = logging.getLogger("app.auth.audit")


def audit(event: str, **fields: object) -> None:
    """Record a security event, e.g. `audit("auth.login.succeeded", user_id=...)`.

    Fields go in both the message, for plain log output, and `extra`, for a
    structured handler. Never pass a secret: no passwords, tokens,
    authorization codes or PKCE verifiers.
    """

    fields = {"request_id": request_id.get(), **fields}
    details = " ".join(f"{key}={value}" for key, value in fields.items())

    logger.info("%s %s", event, details, extra={"event": event, **fields})
