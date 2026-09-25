from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AnalysisRequest:
    """Context given to a provider. It has no database session and no foreign keys to write."""

    content: str
    occurred_at: datetime
    reference_time: datetime
    timezone_name: str
    default_currency: str
