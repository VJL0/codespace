"""The session cookie's attributes, which keep the token out of reach of
scripts, other sites and other hosts."""

from __future__ import annotations

from http.cookies import SimpleCookie

from fastapi import Response

from app.modules.auth.session import delete_session_cookie, set_session_cookie

COOKIE_NAME = "__Host-Http-session"


def parse_set_cookie(response: Response) -> SimpleCookie:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])

    return cookie


def test_session_cookie_is_host_only_secure_and_http_only() -> None:
    response = Response()

    set_session_cookie(response, token="token-value")

    morsel = parse_set_cookie(response)[COOKIE_NAME]
    assert morsel.value == "token-value"
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"] == "lax"
    # The __Host- prefix requires Path=/ and no Domain, or browsers drop it.
    assert morsel["path"] == "/"
    assert morsel["domain"] == ""


def test_deleting_the_cookie_expires_it_with_matching_attributes() -> None:
    response = Response()

    delete_session_cookie(response)

    morsel = parse_set_cookie(response)[COOKIE_NAME]
    assert morsel.value == ""
    assert morsel["max-age"] == "0"
    # Browsers only replace a __Host- cookie set with the same attributes.
    assert morsel["secure"] is True
    assert morsel["path"] == "/"
