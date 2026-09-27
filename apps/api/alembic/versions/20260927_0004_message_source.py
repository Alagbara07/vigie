"""Remember where an imported message came from.

Revision ID: 20260927_0004
Revises: 20260924_0003
Create Date: 2026-09-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0004"
down_revision: str | None = "20260924_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("source", sa.String(length=32), nullable=True))
    op.add_column("messages", sa.Column("external_message_id", sa.String(length=200), nullable=True))
    op.create_check_constraint(
        "ck_messages_source",
        "messages",
        "source IS NULL OR source IN ('whatsapp', 'gmail', 'microsoft365', 'demo')",
    )
    op.create_index(
        "uq_messages_business_source_external",
        "messages",
        ["business_id", "source", "external_message_id"],
        unique=True,
        postgresql_where=sa.text("external_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_business_source_external", table_name="messages")
    op.drop_constraint("ck_messages_source", "messages", type_="check")
    op.drop_column("messages", "external_message_id")
    op.drop_column("messages", "source")
