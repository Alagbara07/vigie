import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import SignalStatus
from app.models import Signal


def find_open_signal(
    session: Session,
    *,
    business_id: uuid.UUID,
    signal_type: str,
    commitment_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
) -> Signal | None:
    statement = select(Signal).where(
        Signal.business_id == business_id,
        Signal.signal_type == signal_type,
        Signal.status == SignalStatus.OPEN.value,
    )
    if commitment_id is not None:
        statement = statement.where(Signal.commitment_id == commitment_id)
    else:
        statement = statement.where(Signal.commitment_id.is_(None), Signal.event_id == event_id)
    return session.scalar(statement)


def persist_new_signal(session: Session, signal: Signal) -> None:
    session.add(signal)
    session.flush()
