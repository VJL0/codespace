"""Security events the auth endpoints record in the audit log."""

from __future__ import annotations

import logging

import httpx2
import pytest

from tests.support.auth_flow import SESSION_COOKIE, approval, complete_flow, sign_in
from tests.support.fake_oauth import FakeOAuthServer


@pytest.fixture
def audit_log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="app.auth.audit")

    return caplog


def events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "app.auth.audit"]


async def test_sign_in_is_recorded_with_user_provider_and_request(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    audit_log: pytest.LogCaptureFixture,
) -> None:
    response = await sign_in(client, fake_oauth, "google", **approval("google"))

    [record] = events(audit_log)
    assert record.event == "auth.login.succeeded"
    assert record.provider == "google"
    assert record.user_id is not None
    assert record.request_id == response.headers["x-request-id"]
    assert "auth.login.succeeded" in record.getMessage()


async def test_failed_sign_in_is_recorded_with_its_reason(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    audit_log: pytest.LogCaptureFixture,
) -> None:
    await sign_in(client, fake_oauth, "google", error="access_denied")

    [record] = events(audit_log)
    assert record.event == "auth.login.failed"
    assert record.provider == "google"
    assert record.reason == "oauth_failed"


async def test_logout_all_is_recorded(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    audit_log: pytest.LogCaptureFixture,
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))
    audit_log.clear()

    await client.post("/api/auth/logout-all")

    [record] = events(audit_log)
    assert record.event == "auth.sessions.revoked_all"


async def test_no_secret_reaches_the_audit_log(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    audit_log: pytest.LogCaptureFixture,
) -> None:
    response = await sign_in(client, fake_oauth, "google", **approval("google"))
    code = response.request.url.params["code"]

    logged = audit_log.text
    assert client.cookies[SESSION_COOKIE] not in logged
    assert code not in logged


async def test_reauthentication_linking_and_unlinking_are_recorded(
    client: httpx2.AsyncClient,
    fake_oauth: FakeOAuthServer,
    audit_log: pytest.LogCaptureFixture,
) -> None:
    await sign_in(client, fake_oauth, "google", **approval("google"))
    await complete_flow(
        client, fake_oauth, "google", "reauthenticate", **approval("google")
    )
    await complete_flow(client, fake_oauth, "github", "link", **approval("github"))
    await client.delete("/api/auth/identities/github")

    assert [record.event for record in events(audit_log)] == [
        "auth.login.succeeded",
        "auth.reauthenticated",
        "auth.oauth.linked",
        "auth.oauth.unlinked",
    ]
