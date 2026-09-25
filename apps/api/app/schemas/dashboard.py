import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ConversationPreviewRead(BaseModel):
    conversation_id: uuid.UUID
    customer_id: uuid.UUID | None
    customer_name: str
    last_message: str
    last_message_at: datetime
    sender_type: str
    direction: str


class DashboardSummaryRead(BaseModel):
    business_id: uuid.UUID
    business_name: str
    timezone: str
    currency: str
    open_signals: int = Field(ge=0)
    high_priority_signals: int = Field(ge=0)
    revenue_at_risk: Decimal = Field(ge=0)
    missed_commitments: int = Field(ge=0)
    opportunity_signals: int = Field(ge=0)
    recent_conversations: list[ConversationPreviewRead]
