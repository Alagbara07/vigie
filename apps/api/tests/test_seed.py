from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessEvent, Commitment, Message, Signal
from app.seed.demo import (
    GREETING_TEXT,
    PAYMENT_CLAIM_TEXT,
    PAYMENT_PROMISE_TEXT,
    UNANSWERED_REQUEST_TEXT,
    seed_demo,
)


def test_seed_is_idempotent_and_creates_no_events(db_session: Session) -> None:
    assert seed_demo(db_session) == 4
    assert seed_demo(db_session) == 0

    contents = set(db_session.scalars(select(Message.content)))
    assert contents == {PAYMENT_CLAIM_TEXT, PAYMENT_PROMISE_TEXT, GREETING_TEXT, UNANSWERED_REQUEST_TEXT}
    assert db_session.scalar(select(func.count()).select_from(Message)) == 4
    assert db_session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
    assert db_session.scalar(select(func.count()).select_from(Commitment)) == 0
    assert db_session.scalar(select(func.count()).select_from(Signal)) == 0

    greeting = db_session.scalar(select(Message).where(Message.content == GREETING_TEXT))
    assert greeting is not None
    assert greeting.content == "Good morning."
