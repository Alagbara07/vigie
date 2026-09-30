import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import EventType, Severity, SignalCategory, SignalStatus, SignalType
from app.evaluators.base import EvaluatorOutcome
from app.evaluators.persist import find_open_signal, persist_new_signal
from app.models import Business, BusinessEvent, Customer, Signal

logger = logging.getLogger(__name__)

RULE_CONFIDENCE = Decimal("1.000")


class PaymentClaimEvaluator:
    """Open one PAYMENT_CLAIM signal for each stored claim.

    The claim stays unverified. This rule does not fulfill a payment commitment.
    """

    name = "payment_claim"

    def evaluate(self, session: Session, business: Business, reference_time: object) -> EvaluatorOutcome:
        del reference_time
        created = 0
        existing = 0
        events = session.scalars(
            select(BusinessEvent).where(
                BusinessEvent.business_id == business.id,
                BusinessEvent.event_type == EventType.PAYMENT_CLAIM.value,
            )
        ).all()
        for event in events:
            if _has_open_signal(session, event):
                existing += 1
                continue
            if _open_signal(session, event):
                created += 1
                logger.info("Opened PAYMENT_CLAIM for event %s", event.id)
            else:
                existing += 1
        return EvaluatorOutcome(signals_created=created, signals_existing=existing, commitments_missed=0)


def _has_open_signal(session: Session, event: BusinessEvent) -> bool:
    return (
        find_open_signal(
            session,
            business_id=event.business_id,
            signal_type=SignalType.PAYMENT_CLAIM.value,
            event_id=event.id,
        )
        is not None
    )


def _open_signal(session: Session, event: BusinessEvent) -> bool:
    try:
        with session.begin_nested():
            persist_new_signal(session, _signal(session, event))
    except IntegrityError:
        found = find_open_signal(
            session,
            business_id=event.business_id,
            signal_type=SignalType.PAYMENT_CLAIM.value,
            event_id=event.id,
        )
        if found is None:
            raise
        return False
    return True


def _signal(session: Session, event: BusinessEvent) -> Signal:
    customer = None if event.customer_id is None else session.get(Customer, event.customer_id)
    who = customer.name if customer is not None else "The customer"
    amount, currency = _money(event.extracted_data)
    if amount is not None and currency is not None:
        description = (
            f"{who} says {currency} {amount} was sent. "
            "VIGIE has not verified the payment."
        )
        impact = amount
    else:
        description = f"{who} says a payment was sent. VIGIE has not verified the payment."
        impact = None
        currency = None
    return Signal(
        business_id=event.business_id,
        signal_type=SignalType.PAYMENT_CLAIM.value,
        category=SignalCategory.RISK.value,
        severity=Severity.HIGH.value,
        title="Payment claim",
        description=description,
        status=SignalStatus.OPEN.value,
        confidence=RULE_CONFIDENCE,
        financial_impact_amount=impact,
        currency=currency,
        event_id=event.id,
        customer_id=event.customer_id,
        commitment_id=None,
    )


def _money(extracted: object) -> tuple[Decimal | None, str | None]:
    if not isinstance(extracted, dict):
        return None, None
    raw_amount = extracted.get("amount")
    raw_currency = extracted.get("currency")
    if not isinstance(raw_amount, str) or not isinstance(raw_currency, str) or not raw_currency.strip():
        return None, None
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        return None, None
    if amount < 0:
        return None, None
    return amount, raw_currency.strip().upper()
