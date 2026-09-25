import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import DuePrecision, EventType, Urgency


class AnalyzeMessageRequest(BaseModel):
    business_id: uuid.UUID
    reference_time: datetime | None = None

    @field_validator("reference_time")
    @classmethod
    def reference_time_has_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("reference_time must include a timezone")
        return value


class MoneyEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        code = value.upper()
        if not code.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return code


class ProposedEvent(BaseModel):
    """What the provider thinks happened. This is not a stored business event."""

    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    confidence: Decimal = Field(ge=0, le=1)
    urgency: Urgency
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    due_at: datetime | None = None
    due_text: str | None = Field(default=None, max_length=200)
    due_precision: DuePrecision | None = None
    description: str = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.upper()
        if not code.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return code

    @field_validator("due_at")
    @classmethod
    def due_at_has_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("due_at must include a timezone")
        return value

    @model_validator(mode="after")
    def amount_and_currency_together(self) -> "ProposedEvent":
        if (self.amount is None) != (self.currency is None):
            raise ValueError("amount and currency must both be set or both be empty")
        return self


class MessageAnalysisProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1, max_length=64)
    confidence: Decimal = Field(ge=0, le=1)
    entities: list[MoneyEntity] = Field(default_factory=list)
    proposed_events: list[ProposedEvent] = Field(default_factory=list)
    reasoning: str = Field(min_length=1)
    provider: str = Field(min_length=1, max_length=64)


class PersistedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    confidence: Decimal
    urgency: str
    extracted_data: dict[str, Any]
    source_message_id: uuid.UUID


class PersistedCommitment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    commitment_type: str
    status: str
    amount: Decimal | None
    currency: str | None
    due_at: datetime | None
    due_text: str | None
    due_precision: str | None
    source_message_id: uuid.UUID
    source_event_id: uuid.UUID | None


class AnalysisRead(BaseModel):
    message_id: uuid.UUID
    business_id: uuid.UUID
    provider: str
    proposal: MessageAnalysisProposal
    events: list[PersistedEvent]
    commitments: list[PersistedCommitment]
