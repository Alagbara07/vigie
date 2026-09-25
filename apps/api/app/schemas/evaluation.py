import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class EvaluationRunRequest(BaseModel):
    business_id: uuid.UUID
    reference_time: datetime

    @field_validator("reference_time")
    @classmethod
    def reference_time_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reference_time must include a timezone")
        return value


class EvaluationRead(BaseModel):
    business_id: uuid.UUID
    reference_time: datetime
    evaluators_run: int = Field(ge=0)
    commitments_missed: int = Field(ge=0)
    signals_created: int = Field(ge=0)
    signals_existing: int = Field(ge=0)
