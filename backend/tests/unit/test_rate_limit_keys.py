"""Which bucket an attempt counts in."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.modules.auth.rate_limit import email_key, ip_key


def request_from(host: str | None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": (host, 1234) if host else None,
        }
    )


def test_email_buckets_are_per_address_without_storing_it() -> None:
    key = email_key("login", "Ada@Example.COM")

    assert key == email_key("login", " Ada@example.com ")
    assert key != email_key("login", "ada@example.com")
    assert key != email_key("signup", "Ada@example.com")
    assert "example" not in key


def test_an_invalid_address_still_gets_a_bucket() -> None:
    assert email_key("login", " nonsense ") == email_key("login", "nonsense")


@pytest.mark.parametrize(
    ("host", "key"),
    [
        ("203.0.113.7", "login:ip:203.0.113.7"),
        # An IPv6 subscriber typically has a whole /64.
        ("2001:db8:1:2:3:4:5:6", "login:ip:2001:db8:1:2::/64"),
        ("testclient", "login:ip:testclient"),
        (None, "login:ip:unknown"),
    ],
)
def test_ip_buckets(host: str | None, key: str) -> None:
    assert ip_key("login", request_from(host)) == key
