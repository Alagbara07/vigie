from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.models import Business


@dataclass(frozen=True)
class EvaluatorOutcome:
    signals_created: int = 0
    signals_existing: int = 0
    commitments_missed: int = 0


class Evaluator(Protocol):
    name: str

    def evaluate(self, session: Session, business: Business, reference_time: datetime) -> EvaluatorOutcome:
        """Inspect one business at reference_time and persist only what the rule requires."""
