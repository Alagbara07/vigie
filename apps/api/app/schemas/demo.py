from datetime import datetime

from pydantic import BaseModel, Field


class DemoModeRead(BaseModel):
    enabled: bool


class DemoResetRead(BaseModel):
    business: str
    messages: int = Field(ge=0)
    events: int = Field(ge=0)
    commitments: int = Field(ge=0)
    signals: int = Field(ge=0)
    actions: int = Field(ge=0)


class DemoRunRead(BaseModel):
    business: str
    provider: str
    messages_analyzed: int = Field(ge=0)
    events_created: int = Field(ge=0)
    commitments_created: int = Field(ge=0)
    commitments_missed: int = Field(ge=0)
    signals_created: int = Field(ge=0)
    actions_created: int = Field(ge=0)
    evaluated_before: datetime
    evaluated_after: datetime
