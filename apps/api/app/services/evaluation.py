import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.errors import NotFoundError
from app.evaluators.base import Evaluator, EvaluatorOutcome
from app.evaluators.overdue_payment import OverduePaymentEvaluator
from app.evaluators.payment_claim import PaymentClaimEvaluator
from app.evaluators.unanswered_request import UnansweredRequestEvaluator
from app.models import Business
from app.schemas.evaluation import EvaluationRead

logger = logging.getLogger(__name__)


def default_evaluators(settings: Settings) -> tuple[Evaluator, ...]:
    return (
        OverduePaymentEvaluator(),
        UnansweredRequestEvaluator(settings.unanswered_request_threshold_minutes),
        PaymentClaimEvaluator(),
    )


def run_evaluation(
    session: Session,
    business_id: uuid.UUID,
    reference_time: datetime,
    evaluators: tuple[Evaluator, ...] | None = None,
) -> EvaluationRead:
    business = session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    active = evaluators if evaluators is not None else default_evaluators(get_settings())
    logger.info(
        "Evaluating business %s at %s with %s evaluators",
        business.id,
        reference_time.isoformat(),
        len(active),
    )
    try:
        totals = _run_all(session, business, reference_time, active)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return EvaluationRead(
        business_id=business.id,
        reference_time=reference_time,
        evaluators_run=len(active),
        commitments_missed=totals.commitments_missed,
        signals_created=totals.signals_created,
        signals_existing=totals.signals_existing,
    )


def _run_all(
    session: Session,
    business: Business,
    reference_time: datetime,
    evaluators: tuple[Evaluator, ...],
) -> EvaluatorOutcome:
    created = 0
    existing = 0
    missed = 0
    for evaluator in evaluators:
        outcome = evaluator.evaluate(session, business, reference_time)
        created += outcome.signals_created
        existing += outcome.signals_existing
        missed += outcome.commitments_missed
    return EvaluatorOutcome(
        signals_created=created,
        signals_existing=existing,
        commitments_missed=missed,
    )
