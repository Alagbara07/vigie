import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import MessageSource, SenderType

SOURCE_LABELS = {
    MessageSource.DEMO: ("WhatsApp Business", "Demo connection"),
    MessageSource.WHATSAPP: ("WhatsApp Business", None),
    MessageSource.GMAIL: ("Google Workspace", None),
    MessageSource.MICROSOFT365: ("Microsoft 365", None),
}


class NormalizedMessage(BaseModel):
    business_id: uuid.UUID
    source: MessageSource
    external_message_id: str = Field(min_length=1, max_length=200)
    external_conversation_id: str = Field(min_length=1, max_length=200)
    external_customer_id: str | None = Field(default=None, max_length=200)
    customer_name: str = Field(min_length=1, max_length=200)
    sender_type: SenderType = SenderType.CUSTOMER
    sender_identifier: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1)
    timestamp: datetime
    metadata: dict[str, Any] | None = None

    @field_validator("external_message_id", "external_conversation_id", "customer_name", "text")
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


def describe_source(source: str | None) -> tuple[str | None, str | None]:
    if source is None:
        return None, None
    try:
        choice = MessageSource(source)
    except ValueError:
        return None, None
    return SOURCE_LABELS[choice]
