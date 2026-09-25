"""Create the VIGIE domain tables.

Revision ID: 20260924_0001
Revises:
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
TIMESTAMPTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("default_currency", sa.String(3), nullable=False, server_default="NGN"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Africa/Lagos"),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_businesses_slug"),
    )
    op.create_table(
        "customers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("business_id", UUID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_identifier", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "business_id", name="uq_customers_id_business"),
        sa.UniqueConstraint("business_id", "contact_identifier", name="uq_customers_business_contact"),
        sa.CheckConstraint("status IN ('ACTIVE', 'UNKNOWN', 'INACTIVE')", name="ck_customers_status"),
    )
    op.create_index("ix_customers_business_id", "customers", ["business_id"])
    op.create_table(
        "conversations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("business_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("external_ref", sa.String(200), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_conversations_customer_business",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "business_id", name="uq_conversations_id_business"),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_conversations_status"),
    )
    op.create_index("ix_conversations_business_id", "conversations", ["business_id"])
    op.create_index(
        "uq_conversations_business_external_ref",
        "conversations",
        ["business_id", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )
    op.create_table(
        "messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("business_id", UUID, nullable=False),
        sa.Column("sender_type", sa.String(32), nullable=False),
        sa.Column("sender_identifier", sa.String(200), nullable=True),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_at", TIMESTAMPTZ, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "business_id"],
            ["conversations.id", "conversations.business_id"],
            name="fk_messages_conversation_business",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "business_id", name="uq_messages_id_business"),
        sa.CheckConstraint(
            "sender_type IN ('customer', 'business', 'system')",
            name="ck_messages_sender_type",
        ),
        sa.CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_messages_direction"),
        sa.CheckConstraint("char_length(content) > 0", name="ck_messages_content_not_blank"),
    )
    op.create_index("ix_messages_conversation_occurred", "messages", ["conversation_id", "occurred_at"])
    op.create_table(
        "business_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("business_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("customer_id", UUID, nullable=True),
        sa.Column("conversation_id", UUID, nullable=True),
        sa.Column("source_message_id", UUID, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("urgency", sa.String(16), nullable=False),
        sa.Column("extracted_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", TIMESTAMPTZ, nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_message_id", "business_id"],
            ["messages.id", "messages.business_id"],
            name="fk_business_events_message_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "business_id"],
            ["conversations.id", "conversations.business_id"],
            name="fk_business_events_conversation_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_business_events_customer_business",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "business_id", name="uq_business_events_id_business"),
        sa.UniqueConstraint(
            "business_id",
            "source_message_id",
            "event_type",
            name="uq_business_events_source_type",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_business_events_confidence"),
        sa.CheckConstraint(
            "urgency IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_business_events_urgency",
        ),
    )
    op.create_index("ix_business_events_business_type", "business_events", ["business_id", "event_type"])
    op.create_table(
        "commitments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("business_id", UUID, nullable=False),
        sa.Column("customer_id", UUID, nullable=True),
        sa.Column("source_event_id", UUID, nullable=True),
        sa.Column("source_message_id", UUID, nullable=False),
        sa.Column("commitment_type", sa.String(64), nullable=False),
        sa.Column("owner_party", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("due_at", TIMESTAMPTZ, nullable=True),
        sa.Column("due_text", sa.String(200), nullable=True),
        sa.Column("due_precision", sa.String(16), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("fulfilled_at", TIMESTAMPTZ, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_message_id", "business_id"],
            ["messages.id", "messages.business_id"],
            name="fk_commitments_message_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_event_id", "business_id"],
            ["business_events.id", "business_events.business_id"],
            name="fk_commitments_event_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_commitments_customer_business",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "business_id", name="uq_commitments_id_business"),
        sa.CheckConstraint(
            "commitment_type IN ('PAYMENT_COMMITMENT', 'CUSTOMER_COMMITMENT', 'SUPPLIER_COMMITMENT', 'EMPLOYEE_COMMITMENT')",
            name="ck_commitments_type",
        ),
        sa.CheckConstraint(
            "owner_party IN ('CUSTOMER', 'BUSINESS', 'SUPPLIER', 'EMPLOYEE')",
            name="ck_commitments_owner",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'FULFILLED', 'MISSED', 'CANCELLED')",
            name="ck_commitments_status",
        ),
        sa.CheckConstraint(
            "due_precision IS NULL OR due_precision IN ('EXACT', 'DATE', 'AMBIGUOUS', 'UNKNOWN')",
            name="ck_commitments_due_precision",
        ),
        sa.CheckConstraint(
            "(amount IS NULL AND currency IS NULL) OR (amount IS NOT NULL AND currency IS NOT NULL AND amount >= 0)",
            name="ck_commitments_amount_currency",
        ),
    )
    op.create_index(
        "ix_commitments_business_status_due",
        "commitments",
        ["business_id", "status", "due_at"],
    )
    op.create_table(
        "signals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("business_id", UUID, nullable=False),
        sa.Column("signal_type", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("financial_impact_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("event_id", UUID, nullable=True),
        sa.Column("customer_id", UUID, nullable=True),
        sa.Column("commitment_id", UUID, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["event_id", "business_id"],
            ["business_events.id", "business_events.business_id"],
            name="fk_signals_event_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_signals_customer_business",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["commitment_id", "business_id"],
            ["commitments.id", "commitments.business_id"],
            name="fk_signals_commitment_business",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "business_id", name="uq_signals_id_business"),
        sa.CheckConstraint(
            "category IN ('REVENUE', 'RISK', 'OPERATIONS', 'COMMITMENT')",
            name="ck_signals_category",
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_signals_severity",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'DISMISSED')",
            name="ck_signals_status",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_signals_confidence"),
        sa.CheckConstraint(
            "(financial_impact_amount IS NULL AND currency IS NULL) OR (financial_impact_amount IS NOT NULL AND currency IS NOT NULL)",
            name="ck_signals_impact_currency",
        ),
    )
    op.create_index("ix_signals_business_status", "signals", ["business_id", "status"])
    op.create_index(
        "uq_signals_one_open_per_commitment",
        "signals",
        ["business_id", "signal_type", "commitment_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN' AND commitment_id IS NOT NULL"),
    )
    op.create_index(
        "uq_signals_one_open_per_event",
        "signals",
        ["business_id", "signal_type", "event_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'OPEN' AND event_id IS NOT NULL AND commitment_id IS NULL"
        ),
    )
    op.create_table(
        "actions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("business_id", UUID, nullable=False),
        sa.Column("signal_id", UUID, nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PROPOSED"),
        sa.Column("proposed_content", sa.Text(), nullable=True),
        sa.Column("approved_at", TIMESTAMPTZ, nullable=True),
        sa.Column("rejected_at", TIMESTAMPTZ, nullable=True),
        sa.Column("executed_at", TIMESTAMPTZ, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["signal_id", "business_id"],
            ["signals.id", "signals.business_id"],
            name="fk_actions_signal_business",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'APPROVED', 'REJECTED', 'EXECUTED')",
            name="ck_actions_status",
        ),
    )
    op.create_index("ix_actions_signal_id", "actions", ["signal_id"])


def downgrade() -> None:
    op.drop_table("actions")
    op.drop_table("signals")
    op.drop_table("commitments")
    op.drop_table("business_events")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("customers")
    op.drop_table("businesses")
