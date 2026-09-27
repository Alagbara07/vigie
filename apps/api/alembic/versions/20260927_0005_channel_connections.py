"""Remember which business owns each communication account.

Revision ID: 20260927_0005
Revises: 20260927_0004
Create Date: 2026-09-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260927_0005"
down_revision: str | None = "20260927_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_account_id", sa.String(length=200), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("business_id", "provider", name="uq_channel_connections_business_provider"),
        sa.CheckConstraint(
            "provider IN ('whatsapp', 'gmail', 'microsoft365', 'demo')",
            name="ck_channel_connections_provider",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'connected', 'disconnected', 'error')",
            name="ck_channel_connections_status",
        ),
    )
    op.create_index("ix_channel_connections_business_id", "channel_connections", ["business_id"])
    op.create_index(
        "uq_channel_connections_account",
        "channel_connections",
        ["provider", "external_account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'connected' AND external_account_id IS NOT NULL"),
    )
    op.create_table(
        "integration_credentials",
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["channel_connections.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("state", sa.String(length=200), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("state", name="uq_oauth_states_state"),
        sa.CheckConstraint("provider IN ('gmail', 'microsoft365')", name="ck_oauth_states_provider"),
    )
    op.create_index("ix_oauth_states_business_id", "oauth_states", ["business_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_states_business_id", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_table("integration_credentials")
    op.drop_index("uq_channel_connections_account", table_name="channel_connections")
    op.drop_index("ix_channel_connections_business_id", table_name="channel_connections")
    op.drop_table("channel_connections")
