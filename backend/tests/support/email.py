"""An email sender that keeps what it's given, for tests to read."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    html: str
    idempotency_key: str

    def link(self) -> str:
        """The email's first link."""

        match = re.search(r'href="([^"]+)"', self.html)
        assert match, self.html

        return match.group(1)

    def token(self) -> str:
        """The secret in the link's #token= fragment."""

        return self.link().split("#token=", 1)[1]


@dataclass
class OutboxEmailSender:
    sent: list[SentEmail] = field(default_factory=list)

    async def send(
        self, *, to: str, subject: str, html: str, idempotency_key: str
    ) -> None:
        self.sent.append(SentEmail(to, subject, html, idempotency_key))

    def to(self, address: str) -> list[SentEmail]:
        return [email for email in self.sent if email.to == address]

    def last_to(self, address: str) -> SentEmail:
        emails = self.to(address)
        assert emails, f"no email to {address}; sent: {self.sent}"

        return emails[-1]
