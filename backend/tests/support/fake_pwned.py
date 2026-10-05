"""A stand-in for the Pwned Passwords range API."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import httpx2

# A password the fake reports as breached, long enough to pass the length
# rule so only the breach check refuses it.
BREACHED_PASSWORD = "correct horse battery staple"


@dataclass
class FakePwnedPasswords:
    breached: set[str] = field(default_factory=lambda: {BREACHED_PASSWORD})
    available: bool = True
    requests: list[httpx2.Request] = field(default_factory=list)

    @property
    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)

        if not self.available:
            return httpx2.Response(503)

        prefix = request.url.path.rsplit("/", 1)[-1]
        lines = [
            f"{digest[5:]}:42"
            for digest in (
                hashlib.sha1(password.encode()).hexdigest().upper()
                for password in self.breached
            )
            if digest.startswith(prefix)
        ]
        # What Add-Padding adds: decoys with a count of 0.
        lines += ["0" * 35 + ":0", "F" * 35 + ":0"]

        return httpx2.Response(200, text="\r\n".join(lines))
