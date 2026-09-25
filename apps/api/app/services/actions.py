import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.actions.rules import draft_for_signal
from app.domain.enums import ActionStatus, SignalStatus
from app.domain.errors import ConflictError, NotFoundError
from app.models import Action, Business, Commitment, Customer, Signal
from app.schemas.actions import ActionRead, ActionSignalSummary, RecommendRead

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Stored:
    action: Action
    created: bool


def recommend_actions(
    session: Session,
    business_id: uuid.UUID,
    signal_id: uuid.UUID | None = None,
) -> RecommendRead:
    business = session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    signals = _target_signals(session, business.id, signal_id)
    created = 0
    existing = 0
    stored: list[Action] = []
    try:
        for signal in signals:
            result = _ensure_action(session, signal)
            if result is None:
                continue
            stored.append(result.action)
            if result.created:
                created += 1
            else:
                existing += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    return RecommendRead(
        business_id=business.id,
        actions_created=created,
        actions_existing=existing,
        actions=[_read(session, action) for action in stored],
    )


def list_actions(
    session: Session,
    business_id: uuid.UUID,
    *,
    status: ActionStatus | None = None,
    signal_id: uuid.UUID | None = None,
) -> list[ActionRead]:
    if session.get(Business, business_id) is None:
        raise NotFoundError("Business not found.")
    statement = select(Action).where(Action.business_id == business_id)
    if status is not None:
        statement = statement.where(Action.status == status.value)
    if signal_id is not None:
        statement = statement.where(Action.signal_id == signal_id)
    statement = statement.order_by(Action.created_at.asc(), Action.id.asc())
    return [_read(session, action) for action in session.scalars(statement).all()]


def get_action(session: Session, action_id: uuid.UUID, business_id: uuid.UUID) -> ActionRead:
    return _read(session, _require_action(session, action_id, business_id))


def approve_action(session: Session, action_id: uuid.UUID, business_id: uuid.UUID) -> ActionRead:
    """Record the owner's approval. This does not contact the customer."""
    action = _require_action(session, action_id, business_id)
    if action.status != ActionStatus.PROPOSED.value:
        raise ConflictError("Only a proposed action can be approved.")
    action.status = ActionStatus.APPROVED.value
    action.approved_at = _decision_time()
    session.commit()
    logger.info("Approved action %s for business %s", action.id, business_id)
    return _read(session, action)


def reject_action(session: Session, action_id: uuid.UUID, business_id: uuid.UUID) -> ActionRead:
    """Record the owner's rejection. This does not contact the customer."""
    action = _require_action(session, action_id, business_id)
    if action.status != ActionStatus.PROPOSED.value:
        raise ConflictError("Only a proposed action can be rejected.")
    action.status = ActionStatus.REJECTED.value
    action.rejected_at = _decision_time()
    session.commit()
    logger.info("Rejected action %s for business %s", action.id, business_id)
    return _read(session, action)


def _decision_time() -> datetime:
    """Wall-clock time of the human decision. Not used to judge due dates."""
    return datetime.now(timezone.utc)


def _target_signals(session: Session, business_id: uuid.UUID, signal_id: uuid.UUID | None) -> list[Signal]:
    if signal_id is None:
        return list(
            session.scalars(
                select(Signal).where(
                    Signal.business_id == business_id,
                    Signal.status == SignalStatus.OPEN.value,
                )
            ).all()
        )
    signal = session.get(Signal, signal_id)
    if signal is None or signal.business_id != business_id:
        raise NotFoundError("Signal not found.")
    if signal.status != SignalStatus.OPEN.value:
        return []
    return [signal]


def _ensure_action(session: Session, signal: Signal) -> _Stored | None:
    customer_name, amount, currency = _facts(session, signal)
    draft = draft_for_signal(
        signal.signal_type,
        customer_name=customer_name,
        amount=amount,
        currency=currency,
    )
    if draft is None:
        return None
    existing = _find(session, signal.business_id, signal.id, draft.action_type)
    if existing is not None:
        return _Stored(existing, created=False)
    action = Action(
        business_id=signal.business_id,
        signal_id=signal.id,
        action_type=draft.action_type,
        title=draft.title,
        description=draft.description,
        proposed_content=draft.proposed_content,
        status=ActionStatus.PROPOSED.value,
    )
    try:
        with session.begin_nested():
            session.add(action)
            session.flush()
    except IntegrityError:
        found = _find(session, signal.business_id, signal.id, draft.action_type)
        if found is None:
            raise
        return _Stored(found, created=False)
    return _Stored(action, created=True)


def _facts(session: Session, signal: Signal) -> tuple[str | None, Decimal | None, str | None]:
    customer = session.get(Customer, signal.customer_id) if signal.customer_id else None
    if customer is not None and customer.business_id != signal.business_id:
        customer = None
    commitment = session.get(Commitment, signal.commitment_id) if signal.commitment_id else None
    if commitment is not None and commitment.business_id != signal.business_id:
        commitment = None
    amount = signal.financial_impact_amount
    currency = signal.currency
    if commitment is not None and commitment.amount is not None and commitment.currency is not None:
        amount = commitment.amount
        currency = commitment.currency
    return (None if customer is None else customer.name), amount, currency


def _find(session: Session, business_id: uuid.UUID, signal_id: uuid.UUID, action_type: str) -> Action | None:
    return session.scalar(
        select(Action).where(
            Action.business_id == business_id,
            Action.signal_id == signal_id,
            Action.action_type == action_type,
        )
    )


def _require_action(session: Session, action_id: uuid.UUID, business_id: uuid.UUID) -> Action:
    action = session.get(Action, action_id)
    if action is None or action.business_id != business_id:
        raise NotFoundError("Action not found.")
    return action


def _read(session: Session, action: Action) -> ActionRead:
    signal = session.get(Signal, action.signal_id)
    if signal is None or signal.business_id != action.business_id:
        raise NotFoundError("Action not found.")
    return ActionRead(
        id=action.id,
        business_id=action.business_id,
        signal_id=action.signal_id,
        action_type=action.action_type,
        title=action.title,
        description=action.description,
        proposed_content=action.proposed_content,
        status=action.status,
        approved_at=action.approved_at,
        rejected_at=action.rejected_at,
        executed_at=action.executed_at,
        created_at=action.created_at,
        updated_at=action.updated_at,
        signal=ActionSignalSummary(
            id=signal.id,
            title=signal.title,
            signal_type=signal.signal_type,
            financial_impact_amount=signal.financial_impact_amount,
            currency=signal.currency,
        ),
    )
