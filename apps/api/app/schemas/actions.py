import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RecommendRequest(BaseModel):
    business_id: uuid.UUID
    signal_id: uuid.UUID | None = None


class ActionDecisionRequest(BaseModel):
    business_id: uuid.UUID


class ActionSignalSummary(BaseModel):
    id: uuid.UUID
    title: str
    signal_type: str
    financial_impact_amount: Decimal | None
    currency: str | None


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    signal_id: uuid.UUID
    action_type: str
    title: str | None
    description: str | None
    proposed_content: str | None
    status: str
    approved_at: datetime | None
    rejected_at: datetime | None
    executed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    signal: ActionSignalSummary


class RecommendRead(BaseModel):
    business_id: uuid.UUID
    actions_created: int = Field(ge=0)
    actions_existing: int = Field(ge=0)
    actions: list[ActionRead]
