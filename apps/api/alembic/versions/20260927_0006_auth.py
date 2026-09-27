"""Add users, memberships, sessions, and audit events.

Revision ID: 20260927_0006
Revises: 20260927_0005
Create Date: 2026-09-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260927_0006"
down_revision: str | None = "20260927_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "business_id", name="uq_memberships_user_business"),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member')", name="ck_memberships_role"),
    )
    op.create_index("ix_memberships_business_id", "memberships", ["business_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_events_business_id", "audit_events", ["business_id"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.add_column(
        "actions",
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_actions_approved_by_user",
        "actions",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "channel_connections",
        sa.Column("connected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_channel_connections_connected_by_user",
        "channel_connections",
        "users",
        ["connected_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "oauth_states",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_oauth_states_user",
        "oauth_states",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_oauth_states_user", "oauth_states", type_="foreignkey")
    op.drop_column("oauth_states", "user_id")
    op.drop_constraint("fk_channel_connections_connected_by_user", "channel_connections", type_="foreignkey")
    op.drop_column("channel_connections", "connected_by_user_id")
    op.drop_constraint("fk_actions_approved_by_user", "actions", type_="foreignkey")
    op.drop_column("actions", "approved_by_user_id")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_business_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_business_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("users")
