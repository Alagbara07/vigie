import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai.provider import AIProvider
from app.demo.clock import AFTER_DUE, BEFORE_DUE
from app.models import Action, Business, BusinessEvent, Commitment, Conversation, Customer, Message, Signal
from app.schemas.demo import DemoResetRead, DemoRunRead
from app.seed.demo import DEMO_NAME, DEMO_SLUG, seed_demo
from app.services.actions import recommend_actions
from app.services.analysis import analyze_stored_message
from app.services.evaluation import run_evaluation

logger = logging.getLogger(__name__)


def reset_demo(session: Session) -> DemoResetRead:
    """Restore Adaeze Wears messages and remove derived rows for that business only."""
    business = session.scalar(select(Business).where(Business.slug == DEMO_SLUG))
    if business is not None:
        _clear_derived_state(session, business.id)
        session.flush()
    seed_demo(session)
    session.commit()
    business = session.scalar(select(Business).where(Business.slug == DEMO_SLUG))
    if business is None:
        raise RuntimeError("Demo business was not created.")
    logger.info("Reset demo business %s", business.slug)
    return _reset_read(session, business)


def run_demo(session: Session, provider: AIProvider) -> DemoRunRead:
    """Replay the Adaeze story through the normal analysis, evaluation, and recommendation services."""
    reset_demo(session)
    business = session.scalar(select(Business).where(Business.slug == DEMO_SLUG))
    if business is None:
        raise RuntimeError("Demo business was not created.")
    messages = list(
        session.scalars(
            select(Message)
            .where(Message.business_id == business.id)
            .order_by(Message.occurred_at.asc(), Message.id.asc())
        ).all()
    )
    events_before = _count(session, BusinessEvent, business.id)
    commitments_before = _count(session, Commitment, business.id)
    for message in messages:
        analyze_stored_message(session, message.id, business.id, BEFORE_DUE, provider)
    before = run_evaluation(session, business.id, BEFORE_DUE)
    after = run_evaluation(session, business.id, AFTER_DUE)
    recommended = recommend_actions(session, business.id)
    logger.info(
        "Demo run for %s provider=%s messages=%s signals=%s",
        business.slug,
        provider.name,
        len(messages),
        after.signals_created,
    )
    return DemoRunRead(
        business=business.name,
        provider=provider.name,
        messages_analyzed=len(messages),
        events_created=_count(session, BusinessEvent, business.id) - events_before,
        commitments_created=_count(session, Commitment, business.id) - commitments_before,
        commitments_missed=before.commitments_missed + after.commitments_missed,
        signals_created=before.signals_created + after.signals_created,
        actions_created=recommended.actions_created,
        evaluated_before=BEFORE_DUE,
        evaluated_after=AFTER_DUE,
    )


def _clear_derived_state(session: Session, business_id: uuid.UUID) -> None:
    for model in (Action, Signal, Commitment, BusinessEvent, Message, Conversation, Customer):
        session.execute(delete(model).where(model.business_id == business_id))


def _reset_read(session: Session, business: Business) -> DemoResetRead:
    return DemoResetRead(
        business=business.name or DEMO_NAME,
        messages=_count(session, Message, business.id),
        events=_count(session, BusinessEvent, business.id),
        commitments=_count(session, Commitment, business.id),
        signals=_count(session, Signal, business.id),
        actions=_count(session, Action, business.id),
    )


def _count(session: Session, model: type, business_id: uuid.UUID) -> int:
    return int(
        session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id)) or 0
    )
