import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ChannelStatusRead(BaseModel):
    provider: str
    label: str
    description: str
    availability: str
    account_label: str | None
    connected_at: datetime | None
    last_sync_at: datetime | None
    last_error: str | None
    configured: bool
    listening: bool = False
    realtime: str = "not_configured"
    last_notification_at: datetime | None = None
    pubsub_configured: bool = False
    webhook_url: str | None = None


class WhatsAppConnectRequest(BaseModel):
    business_id: uuid.UUID
    phone_number_id: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)

    @field_validator("phone_number_id", "display_name")
    @classmethod
    def not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class DisconnectRequest(BaseModel):
    business_id: uuid.UUID


class SyncRead(BaseModel):
    stored: int
