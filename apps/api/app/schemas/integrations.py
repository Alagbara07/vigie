import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DemoMessageCreate(BaseModel):
    business_id: uuid.UUID
    customer_name: str = Field(min_length=1, max_length=200)
    conversation_id: str = Field(min_length=1, max_length=200)
    external_message_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    timestamp: datetime

    @field_validator("customer_name", "conversation_id", "external_message_id", "text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class DemoMessageRead(BaseModel):
    created: bool
    analyzed: bool
    message_id: uuid.UUID
    business_id: uuid.UUID
    source: str
    source_label: str
    connection: str | None
    external_message_id: str
    customer_name: str
    text: str
    occurred_at: datetime
    events: list[str]


class DemoMessageListItem(BaseModel):
    message_id: uuid.UUID
    customer_name: str
    text: str
    occurred_at: datetime
    external_message_id: str
    source_label: str
    connection: str | None
    events: list[str]
