import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import (
    CommitmentStatus,
    CommitmentType,
    Severity,
    SignalCategory,
    SignalStatus,
    SignalType,
)
from app.evaluators.base import EvaluatorOutcome
from app.evaluators.persist import find_open_signal, persist_new_signal
from app.evaluators.time import is_past_due
from app.models import Business, Commitment, Customer, Signal

logger = logging.getLogger(__name__)

RULE_CONFIDENCE = Decimal("1.000")


@dataclass(frozen=True)
class _OverdueWrite:
    created: bool
    newly_missed: bool


class OverduePaymentEvaluator:
    """Mark a pending payment commitment missed and open one OVERDUE_PAYMENT signal.

    A PAYMENT_CLAIM is never read here. Saying the money was sent does not fulfill
    the commitment and does not stop this rule.
    """

    name = "overdue_payment"

    def evaluate(self, session: Session, business: Business, reference_time: datetime) -> EvaluatorOutcome:
        created = 0
        existing = 0
        missed = 0
        commitments = session.scalars(
            select(Commitment).where(
                Commitment.business_id == business.id,
                Commitment.commitment_type == CommitmentType.PAYMENT_COMMITMENT.value,
                Commitment.status.in_((CommitmentStatus.PENDING.value, CommitmentStatus.MISSED.value)),
                Commitment.due_at.is_not(None),
            )
        ).all()
        for commitment in commitments:
            if not is_past_due(commitment.due_at, commitment.due_precision, reference_time, business.timezone):
                continue
            outcome = _ensure_overdue_signal(session, business, commitment)
            if outcome.created:
                created += 1
            else:
                existing += 1
            if outcome.newly_missed:
                missed += 1
        return EvaluatorOutcome(
            signals_created=created,
            signals_existing=existing,
            commitments_missed=missed,
        )


def _ensure_overdue_signal(session: Session, business: Business, commitment: Commitment) -> _OverdueWrite:
    open_signal = find_open_signal(
        session,
        business_id=commitment.business_id,
        signal_type=SignalType.OVERDUE_PAYMENT.value,
        commitment_id=commitment.id,
    )
    if open_signal is not None:
        newly_missed = commitment.status == CommitmentStatus.PENDING.value
        if newly_missed:
            commitment.status = CommitmentStatus.MISSED.value
            session.flush()
        return _OverdueWrite(created=False, newly_missed=newly_missed)

    was_pending = commitment.status == CommitmentStatus.PENDING.value
    try:
        with session.begin_nested():
            commitment.status = CommitmentStatus.MISSED.value
            persist_new_signal(session, _signal(session, business, commitment))
    except IntegrityError:
        session.refresh(commitment)
        open_signal = find_open_signal(
            session,
            business_id=commitment.business_id,
            signal_type=SignalType.OVERDUE_PAYMENT.value,
            commitment_id=commitment.id,
        )
        if open_signal is None:
            raise
        newly_missed = commitment.status == CommitmentStatus.PENDING.value
        commitment.status = CommitmentStatus.MISSED.value
        session.flush()
        return _OverdueWrite(created=False, newly_missed=newly_missed)
    if was_pending:
        logger.info("Commitment %s is missed; opened OVERDUE_PAYMENT", commitment.id)
    return _OverdueWrite(created=True, newly_missed=was_pending)


def _signal(session: Session, business: Business, commitment: Commitment) -> Signal:
    customer = None if commitment.customer_id is None else session.get(Customer, commitment.customer_id)
    who = customer.name if customer is not None else "The customer"
    when = commitment.due_text or "the due date"
    if commitment.amount is not None and commitment.currency is not None:
        money = f"{commitment.currency} {_amount(commitment.amount)}"
        description = (
            f"{who} promised {money} by {when}. "
            "The commitment has not been fulfilled. "
            f"Revenue at risk: {money}."
        )
        impact = commitment.amount
        currency = commitment.currency
    else:
        description = f"{who} promised a payment by {when}. The commitment has not been fulfilled."
        impact = None
        currency = None
    return Signal(
        business_id=business.id,
        signal_type=SignalType.OVERDUE_PAYMENT.value,
        category=SignalCategory.REVENUE.value,
        severity=Severity.HIGH.value,
        title="Payment overdue",
        description=description,
        status=SignalStatus.OPEN.value,
        confidence=RULE_CONFIDENCE,
        financial_impact_amount=impact,
        currency=currency,
        event_id=commitment.source_event_id,
        customer_id=commitment.customer_id,
        commitment_id=commitment.id,
    )


def _amount(amount: Decimal) -> str:
    rendered = format(amount.quantize(Decimal("0.01")), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered
