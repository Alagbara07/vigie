import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    signal_type: str
    category: str
    severity: str
    title: str
    description: str
    status: str
    confidence: Decimal
    financial_impact_amount: Decimal | None
    currency: str | None
    event_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    commitment_id: uuid.UUID | None
    created_at: datetime
    customer_name: str | None = None
    attention_group: str


class CustomerBrief(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime


class CommitmentBrief(BaseModel):
    id: uuid.UUID
    commitment_type: str
    status: str
    amount: Decimal | None
    currency: str | None
    due_at: datetime | None
    due_text: str | None
    description: str


class EventBrief(BaseModel):
    id: uuid.UUID
    event_type: str
    occurred_at: datetime
    description: str | None


class EvidenceRead(BaseModel):
    message_id: uuid.UUID
    content: str
    sender_type: str
    direction: str
    occurred_at: datetime


class ConversationBrief(BaseModel):
    id: uuid.UUID
    channel: str
    message_count: int


class ActionBrief(BaseModel):
    id: uuid.UUID
    action_type: str
    title: str | None = None
    description: str | None = None
    status: str
    proposed_content: str | None = None


class SignalListRead(SignalRead):
    action: ActionBrief | None = None


class SignalDetailRead(SignalRead):
    timezone: str
    customer: CustomerBrief | None
    commitment: CommitmentBrief | None
    event: EventBrief | None
    evidence: EvidenceRead | None
    conversation: ConversationBrief | None
    action: ActionBrief | None
