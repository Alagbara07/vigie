import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (UniqueConstraint("slug", name="uq_businesses_slug"),)

    id: Mapped[uuid.UUID] = _uuid()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    default_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="NGN",
        server_default="NGN",
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Africa/Lagos",
        server_default="Africa/Lagos",
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("id", "business_id", name="uq_customers_id_business"),
        UniqueConstraint(
            "business_id",
            "contact_identifier",
            name="uq_customers_business_contact",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'UNKNOWN', 'INACTIVE')",
            name="ck_customers_status",
        ),
        Index("ix_customers_business_id", "business_id"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("id", "business_id", name="uq_conversations_id_business"),
        ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_conversations_customer_business",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_conversations_status"),
        Index(
            "uq_conversations_business_external_ref",
            "business_id",
            "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
        Index("ix_conversations_business_id", "business_id"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", server_default="OPEN")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Message(Base):
    """Original conversation text. AI output is never written back into content."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("id", "business_id", name="uq_messages_id_business"),
        ForeignKeyConstraint(
            ["conversation_id", "business_id"],
            ["conversations.id", "conversations.business_id"],
            name="fk_messages_conversation_business",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "sender_type IN ('customer', 'business', 'system')",
            name="ck_messages_sender_type",
        ),
        CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name="ck_messages_direction",
        ),
        CheckConstraint("char_length(content) > 0", name="ck_messages_content_not_blank"),
        CheckConstraint(
            "source IS NULL OR source IN ('whatsapp', 'gmail', 'microsoft365', 'demo')",
            name="ck_messages_source",
        ),
        Index(
            "uq_messages_business_source_external",
            "business_id",
            "source",
            "external_message_id",
            unique=True,
            postgresql_where=text("external_message_id IS NOT NULL"),
        ),
        Index("ix_messages_conversation_occurred", "conversation_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    conversation_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sender_identifier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class BusinessEvent(Base):
    __tablename__ = "business_events"
    __table_args__ = (
        UniqueConstraint("id", "business_id", name="uq_business_events_id_business"),
        UniqueConstraint(
            "business_id",
            "source_message_id",
            "event_type",
            name="uq_business_events_source_type",
        ),
        ForeignKeyConstraint(
            ["source_message_id", "business_id"],
            ["messages.id", "messages.business_id"],
            name="fk_business_events_message_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "business_id"],
            ["conversations.id", "conversations.business_id"],
            name="fk_business_events_conversation_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_business_events_customer_business",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_business_events_confidence",
        ),
        CheckConstraint(
            "urgency IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_business_events_urgency",
        ),
        Index("ix_business_events_business_type", "business_id", "event_type"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_message_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
    extracted_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class Commitment(Base):
    __tablename__ = "commitments"
    __table_args__ = (
        UniqueConstraint("id", "business_id", name="uq_commitments_id_business"),
        ForeignKeyConstraint(
            ["source_message_id", "business_id"],
            ["messages.id", "messages.business_id"],
            name="fk_commitments_message_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_event_id", "business_id"],
            ["business_events.id", "business_events.business_id"],
            name="fk_commitments_event_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_commitments_customer_business",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "commitment_type IN ('PAYMENT_COMMITMENT', 'CUSTOMER_COMMITMENT', 'SUPPLIER_COMMITMENT', 'EMPLOYEE_COMMITMENT')",
            name="ck_commitments_type",
        ),
        CheckConstraint(
            "owner_party IN ('CUSTOMER', 'BUSINESS', 'SUPPLIER', 'EMPLOYEE')",
            name="ck_commitments_owner",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'FULFILLED', 'MISSED', 'CANCELLED')",
            name="ck_commitments_status",
        ),
        CheckConstraint(
            "due_precision IS NULL OR due_precision IN ('EXACT', 'DATE', 'AMBIGUOUS', 'UNKNOWN')",
            name="ck_commitments_due_precision",
        ),
        CheckConstraint(
            "(amount IS NULL AND currency IS NULL) OR (amount IS NOT NULL AND currency IS NOT NULL AND amount >= 0)",
            name="ck_commitments_amount_currency",
        ),
        UniqueConstraint(
            "business_id",
            "source_message_id",
            "commitment_type",
            name="uq_commitments_source_type",
        ),
        Index("ix_commitments_business_status_due", "business_id", "status", "due_at"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_message_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    commitment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_party: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_precision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", server_default="PENDING")
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("id", "business_id", name="uq_signals_id_business"),
        ForeignKeyConstraint(
            ["event_id", "business_id"],
            ["business_events.id", "business_events.business_id"],
            name="fk_signals_event_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_id", "business_id"],
            ["customers.id", "customers.business_id"],
            name="fk_signals_customer_business",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["commitment_id", "business_id"],
            ["commitments.id", "commitments.business_id"],
            name="fk_signals_commitment_business",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "category IN ('REVENUE', 'RISK', 'OPERATIONS', 'COMMITMENT')",
            name="ck_signals_category",
        ),
        CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_signals_severity",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'DISMISSED')",
            name="ck_signals_status",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_signals_confidence"),
        CheckConstraint(
            "(financial_impact_amount IS NULL AND currency IS NULL) OR (financial_impact_amount IS NOT NULL AND currency IS NOT NULL)",
            name="ck_signals_impact_currency",
        ),
        Index(
            "uq_signals_one_open_per_commitment",
            "business_id",
            "signal_type",
            "commitment_id",
            unique=True,
            postgresql_where=text("status = 'OPEN' AND commitment_id IS NOT NULL"),
        ),
        Index(
            "uq_signals_one_open_per_event",
            "business_id",
            "signal_type",
            "event_id",
            unique=True,
            postgresql_where=text("status = 'OPEN' AND event_id IS NOT NULL AND commitment_id IS NULL"),
        ),
        Index("ix_signals_business_status", "business_id", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", server_default="OPEN")
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    financial_impact_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    commitment_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Action(Base):
    """A recommended or recorded decision. Approval does not send a message."""

    __tablename__ = "actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["signal_id", "business_id"],
            ["signals.id", "signals.business_id"],
            name="fk_actions_signal_business",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'APPROVED', 'REJECTED', 'EXECUTED')",
            name="ck_actions_status",
        ),
        UniqueConstraint(
            "business_id",
            "signal_id",
            "action_type",
            name="uq_actions_signal_type",
        ),
        Index("ix_actions_signal_id", "signal_id"),
    )

    id: Mapped[uuid.UUID] = _uuid()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    signal_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROPOSED", server_default="PROPOSED")
    proposed_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
