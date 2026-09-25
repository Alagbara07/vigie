import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import Direction, EventType, SenderType, Severity, SignalCategory, SignalStatus, SignalType
from app.evaluators.base import EvaluatorOutcome
from app.evaluators.persist import find_open_signal, persist_new_signal
from app.models import Business, BusinessEvent, Message, Signal

logger = logging.getLogger(__name__)

RULE_CONFIDENCE = Decimal("1.000")


class UnansweredRequestEvaluator:
    """Open one UNANSWERED_REQUEST signal when a stored request has no business reply.

    Reply detection uses message direction and sender. It does not call a model.
    """

    name = "unanswered_request"

    def __init__(self, threshold_minutes: int) -> None:
        if threshold_minutes < 0:
            raise ValueError("unanswered request threshold must be zero or greater")
        self.threshold_minutes = threshold_minutes

    def evaluate(self, session: Session, business: Business, reference_time: datetime) -> EvaluatorOutcome:
        created = 0
        existing = 0
        events = session.scalars(
            select(BusinessEvent).where(
                BusinessEvent.business_id == business.id,
                BusinessEvent.event_type == EventType.UNANSWERED_REQUEST.value,
            )
        ).all()
        for event in events:
            if _has_open_signal(session, event):
                existing += 1
                continue
            if _business_has_replied(session, event, reference_time):
                continue
            if reference_time < event.occurred_at + timedelta(minutes=self.threshold_minutes):
                continue
            if _open_signal(session, event):
                created += 1
                logger.info("Opened UNANSWERED_REQUEST for event %s", event.id)
            else:
                existing += 1
        return EvaluatorOutcome(signals_created=created, signals_existing=existing, commitments_missed=0)


def _has_open_signal(session: Session, event: BusinessEvent) -> bool:
    return (
        find_open_signal(
            session,
            business_id=event.business_id,
            signal_type=SignalType.UNANSWERED_REQUEST.value,
            event_id=event.id,
        )
        is not None
    )


def _business_has_replied(session: Session, event: BusinessEvent, reference_time: datetime) -> bool:
    if event.conversation_id is None:
        return False
    reply_id = session.scalar(
        select(Message.id).where(
            Message.business_id == event.business_id,
            Message.conversation_id == event.conversation_id,
            Message.direction == Direction.OUTBOUND.value,
            Message.sender_type == SenderType.BUSINESS.value,
            Message.occurred_at > event.occurred_at,
            Message.occurred_at <= reference_time,
        )
    )
    return reply_id is not None


def _open_signal(session: Session, event: BusinessEvent) -> bool:
    try:
        with session.begin_nested():
            persist_new_signal(session, _signal(event))
    except IntegrityError:
        found = find_open_signal(
            session,
            business_id=event.business_id,
            signal_type=SignalType.UNANSWERED_REQUEST.value,
            event_id=event.id,
        )
        if found is None:
            raise
        return False
    return True


def _signal(event: BusinessEvent) -> Signal:
    detail = ""
    if isinstance(event.extracted_data, dict):
        detail = str(event.extracted_data.get("description") or "").strip()
    if not detail:
        detail = "The customer asked a question."
    return Signal(
        business_id=event.business_id,
        signal_type=SignalType.UNANSWERED_REQUEST.value,
        category=SignalCategory.OPERATIONS.value,
        severity=Severity.MEDIUM.value,
        title="Unanswered request",
        description=f"{detail} The business has not replied.",
        status=SignalStatus.OPEN.value,
        confidence=RULE_CONFIDENCE,
        financial_impact_amount=None,
        currency=None,
        event_id=event.id,
        customer_id=event.customer_id,
        commitment_id=None,
    )
