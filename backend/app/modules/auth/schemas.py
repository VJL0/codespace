from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CurrentUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(validation_alias="full_name")
    email: str
    avatar_url: str | None
