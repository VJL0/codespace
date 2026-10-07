"""move emails to user_emails and allow several oauth accounts

Revision ID: 241a5296e431
Revises: 7438350d33ac
Create Date: 2026-10-05 04:29:21.875982+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "241a5296e431"
down_revision: str | Sequence[str] | None = "7438350d33ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_emails",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("normalized_email", sa.String(length=254), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT is_primary OR verified_at IS NOT NULL",
            name=op.f("ck_user_emails_primary_is_verified"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_emails_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_emails")),
        sa.UniqueConstraint(
            "user_id",
            "normalized_email",
            name=op.f("uq_user_emails_user_id_normalized_email"),
        ),
    )
    op.create_index(
        "uq_user_emails_normalized_email_verified",
        "user_emails",
        ["normalized_email"],
        unique=True,
        postgresql_where=sa.text("verified_at IS NOT NULL"),
    )
    op.create_index(
        "uq_user_emails_user_id_primary",
        "user_emails",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    # Every existing email came from a provider that verified it. They were
    # stored lowercased, which the email-validator normal form (domain
    # lowercased, local part as given) treats as the same address.
    op.execute(
        "INSERT INTO user_emails"
        " (id, user_id, email, normalized_email, verified_at, is_primary)"
        " SELECT uuidv7(), id, email, email, created_at, true FROM users"
    )

    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    op.drop_constraint(op.f("ck_users_email_not_empty"), "users", type_="check")
    op.drop_column("users", "email")

    op.drop_constraint(
        op.f("uq_oauth_accounts_user_id"), "oauth_accounts", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_oauth_accounts_user_id_provider"),
        "oauth_accounts",
        ["user_id", "provider"],
    )
    op.alter_column(
        "oauth_accounts", "provider_email", new_column_name="email_snapshot"
    )
    op.drop_column("oauth_accounts", "provider_email_verified")


def downgrade() -> None:
    """Downgrade schema."""
    # The old schema holds one email and one OAuth account per user; refuse
    # rather than drop users or accounts it can't represent.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT FROM users u WHERE NOT EXISTS (
                    SELECT FROM user_emails e WHERE e.user_id = u.id AND e.is_primary
                )
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: a user has no primary email.';
            END IF;
            IF EXISTS (
                SELECT FROM oauth_accounts GROUP BY user_id HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: a user has several OAuth accounts.';
            END IF;
        END
        $$
        """
    )

    op.add_column(
        "oauth_accounts",
        sa.Column(
            "provider_email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.alter_column(
        "oauth_accounts", "email_snapshot", new_column_name="provider_email"
    )
    op.drop_constraint(
        op.f("uq_oauth_accounts_user_id_provider"), "oauth_accounts", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_oauth_accounts_user_id"), "oauth_accounts", ["user_id"]
    )

    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.execute(
        "UPDATE users SET email = lower(e.email)"
        " FROM user_emails e WHERE e.user_id = users.id AND e.is_primary"
    )
    op.alter_column("users", "email", nullable=False)
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])
    op.create_check_constraint(
        op.f("ck_users_email_not_empty"), "users", "length(email) > 0"
    )

    op.drop_index(
        "uq_user_emails_user_id_primary",
        table_name="user_emails",
        postgresql_where=sa.text("is_primary"),
    )
    op.drop_index(
        "uq_user_emails_normalized_email_verified",
        table_name="user_emails",
        postgresql_where=sa.text("verified_at IS NOT NULL"),
    )
    op.drop_table("user_emails")
