from __future__ import annotations

from pydantic import BaseModel


class CurrentUserRead(BaseModel):
    name: str | None
    # The primary verified email; a user who signed in with a provider that
    # vouched for none has no email.
    email: str | None
    avatar_url: str | None
