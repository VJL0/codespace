from __future__ import annotations

import secrets
import string


PUBLIC_ID_ALPHABET = string.ascii_letters + string.digits
PUBLIC_ID_LENGTH = 12


def generate_public_id(length: int = PUBLIC_ID_LENGTH) -> str:
    return "".join(secrets.choice(PUBLIC_ID_ALPHABET) for _ in range(length))
