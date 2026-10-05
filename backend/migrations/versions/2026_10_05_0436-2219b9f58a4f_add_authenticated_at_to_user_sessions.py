"""add authenticated_at to user sessions

Revision ID: 2219b9f58a4f
Revises: 241a5296e431
Create Date: 2026-10-05 04:36:14.173452+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2219b9f58a4f"
down_revision: str | Sequence[str] | None = "241a5296e431"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing sessions came from provider sign-ins, none of them fresh.
    op.add_column(
        "user_sessions",
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_sessions", "authenticated_at")
