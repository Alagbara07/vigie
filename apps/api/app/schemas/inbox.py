import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import Channel, ConversationStatus, CustomerStatus, Direction, SenderType

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    default_currency: str = Field(default="NGN", min_length=3, max_length=3)
    timezone: str = Field(default="Africa/Lagos", min_length=1, max_length=64)

    @field_validator("slug")
    @classmethod
    def slug_shape(cls, value: str | None) -> str | None:
        if value is not None and _SLUG.fullmatch(value) is None:
            raise ValueError("slug must be lowercase letters, numbers, and hyphens")
        return value

    @field_validator("default_currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        code = value.upper()
        if not code.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return code


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    default_currency: str
    timezone: str
    created_at: datetime
    updated_at: datetime


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_identifier: str = Field(min_length=1, max_length=200)
    status: CustomerStatus = CustomerStatus.ACTIVE


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    contact_identifier: str
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    customer_id: uuid.UUID | None = None
    channel: Channel = Channel.SIMULATED
    external_ref: str | None = Field(default=None, max_length=200)
    status: ConversationStatus = ConversationStatus.OPEN


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID | None
    channel: Channel
    external_ref: str | None
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    sender_type: SenderType
    sender_identifier: str | None = Field(default=None, max_length=200)
    direction: Direction
    content: str = Field(min_length=1)
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    business_id: uuid.UUID
    sender_type: SenderType
    sender_identifier: str | None
    direction: Direction
    content: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="message_metadata")
    created_at: datetime
