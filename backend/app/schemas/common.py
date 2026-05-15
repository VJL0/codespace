from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

"""
Routes can use:

public_id: PublicId

That means invalid IDs fail before hitting the database.
"""
PublicId = Annotated[
    str,
    StringConstraints(
        min_length=12,
        max_length=12,
        pattern=r"^[A-Za-z0-9]{12}$",
    ),
]
