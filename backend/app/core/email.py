import logging
from collections.abc import Mapping
from typing import Any, Protocol

import httpx2
import resend
from resend.http_client_async import AsyncHTTPClient

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send(
        self, *, to: str, subject: str, html: str, idempotency_key: str
    ) -> None:
        """Send one email. `idempotency_key` names the operation, so a
        retried send of it is delivered once."""


class ResendEmailSender:
    def __init__(self, sender: str) -> None:
        self._sender = sender

    async def send(
        self, *, to: str, subject: str, html: str, idempotency_key: str
    ) -> None:
        await resend.Emails.send_async(
            {"from": self._sender, "to": [to], "subject": subject, "html": html},
            options={"idempotency_key": idempotency_key},
        )


class LogEmailSender:
    """Development: logs each email, links included, instead of sending it."""

    async def send(
        self, *, to: str, subject: str, html: str, idempotency_key: str
    ) -> None:
        logger.info("Email to %s: %s\n%s", to, subject, html)


class Httpx2ResendClient(AsyncHTTPClient):
    """Resend's async transport on the app's shared httpx2 client, instead of
    the `resend[async]` extra's httpx."""

    def __init__(self, client: httpx2.AsyncClient) -> None:
        self._client = client

    async def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json: dict[str, object] | list[object] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
    ) -> tuple[bytes, int, Mapping[str, str]]:
        try:
            response = await self._client.request(
                method,
                url,
                headers=headers,
                json=json if data is None and files is None else None,
                data=data,
                files=files,
            )
        except httpx2.HTTPError as exc:
            # What Resend's own clients raise, which it reports as a ResendError.
            raise RuntimeError(f"Request failed: {exc}") from exc

        return response.content, response.status_code, response.headers
