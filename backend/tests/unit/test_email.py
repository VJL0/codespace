"""Sending email: Resend over the app's httpx2 client, or the log."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx2
import pytest
import resend
from resend.exceptions import ResendError

from app.core.config import settings
from app.core.email import (
    Httpx2ResendClient,
    LogEmailSender,
    ResendEmailSender,
)
from app.lifespan import create_email_sender


@pytest.fixture(autouse=True)
def isolated_resend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The Resend SDK is configured through module globals.
    monkeypatch.setattr(resend, "api_key", "re_test")
    monkeypatch.setattr(resend, "default_async_http_client", None)
    yield


def resend_answering(handler: httpx2.MockTransport) -> None:
    resend.default_async_http_client = Httpx2ResendClient(
        httpx2.AsyncClient(transport=handler)
    )


async def send() -> None:
    await ResendEmailSender("CodeSpace <no-reply@example.com>").send(
        to="ada@example.com",
        subject="Hello",
        html="<p>Hi</p>",
        idempotency_key="signup/123",
    )


async def test_resend_gets_the_email_with_its_idempotency_key() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": "email-id"})

    resend_answering(httpx2.MockTransport(handler))

    await send()

    [request] = requests
    assert request.method == "POST"
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["idempotency-key"] == "signup/123"
    assert request.headers["authorization"] == "Bearer re_test"
    assert json.loads(request.content) == {
        "from": "CodeSpace <no-reply@example.com>",
        "to": ["ada@example.com"],
        "subject": "Hello",
        "html": "<p>Hi</p>",
    }


async def test_a_network_failure_is_a_resend_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("unreachable", request=request)

    resend_answering(httpx2.MockTransport(handler))

    with pytest.raises(ResendError):
        await send()


@pytest.mark.parametrize(
    ("environment", "sender_type"),
    [
        ("production", ResendEmailSender),
        ("development", LogEmailSender),
        ("test", LogEmailSender),
    ],
)
async def test_only_production_sends_through_resend(
    monkeypatch: pytest.MonkeyPatch, environment: str, sender_type: type
) -> None:
    monkeypatch.setattr(settings, "environment", environment)

    async with httpx2.AsyncClient() as http_client:
        assert isinstance(create_email_sender(http_client), sender_type)
