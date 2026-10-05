import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# What a proxy's ID may look like; anything else is replaced, so a client
# can't write arbitrary text into the logs.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")


class RequestIdMiddleware:
    """Tags each request with an ID, for logs and the X-Request-ID header.

    The edge's ID is kept when it sends one, so a request can be followed
    from the proxy's logs into the app's.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        value = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = value

            await send(message)

        token = request_id.set(value)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id.reset(token)
