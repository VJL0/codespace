from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class Message:
    subject: str
    html: str


def _link(path: str, secret: str) -> str:
    # In the fragment, which browsers don't send: the secret stays out of
    # server and proxy logs, and the page posts it to the API itself.
    return f"{settings.app_url}{path}#token={secret}"


def _button(url: str, label: str) -> str:
    return f'<p><a href="{url}">{label}</a></p>'


def signup(secret: str) -> Message:
    return Message(
        subject="Finish creating your CodeSpace account",
        html=(
            "<p>Use this link within an hour to finish creating your account.</p>"
            + _button(_link("/signup/complete", secret), "Finish signing up")
            + "<p>If you didn't ask for this, ignore this email.</p>"
        ),
    )


def account_exists() -> Message:
    # Sent instead of a signup link, so the signup form doesn't reveal which
    # addresses have accounts: only the address's owner learns it.
    return Message(
        subject="You already have a CodeSpace account",
        html=(
            "<p>Someone tried to sign up with this address, which already has an"
            " account. If it was you, sign in instead.</p>"
            + _button(f"{settings.app_url}/login", "Sign in")
            + "<p>If it wasn't you, ignore this email.</p>"
        ),
    )


def reauthentication(secret: str) -> Message:
    return Message(
        subject="Confirm it's you",
        html=(
            "<p>Open this link within 15 minutes, in the browser where you asked"
            " for it, to confirm it's you.</p>"
            + _button(_link("/reauthenticate", secret), "Confirm it's me")
            + "<p>If you didn't ask for this, someone may be using your session:"
            " sign out everywhere from your settings.</p>"
        ),
    )


def password_reset(secret: str) -> Message:
    return Message(
        subject="Reset your CodeSpace password",
        html=(
            "<p>Use this link within 30 minutes to choose a new password. It"
            " signs you out everywhere.</p>"
            + _button(_link("/reset-password", secret), "Reset password")
            + "<p>If you didn't ask for this, ignore this email: your password"
            " stays as it is.</p>"
        ),
    )


def password_setup(secret: str) -> Message:
    return Message(
        subject="Add a password to your CodeSpace account",
        html=(
            "<p>Use this link within 30 minutes to add a password, so you can"
            " also sign in with your email.</p>"
            + _button(_link("/password-setup", secret), "Add a password")
            + "<p>If you didn't ask for this, someone may be using your session:"
            " sign out everywhere from your settings.</p>"
        ),
    )
