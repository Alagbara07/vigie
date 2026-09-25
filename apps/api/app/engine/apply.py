from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import CommitmentOwner, CommitmentStatus, CommitmentType, EventType
from app.models import BusinessEvent, Commitment, Conversation, Message
from app.schemas.analysis import MessageAnalysisProposal, ProposedEvent


@dataclass(frozen=True)
class AppliedAnalysis:
    events: list[BusinessEvent]
    commitments: list[Commitment]


def apply_proposal(
    session: Session,
    message: Message,
    conversation: Conversation,
    proposal: MessageAnalysisProposal,
) -> AppliedAnalysis:
    """Persist events and commitments. A claim never becomes a verified payment or a signal."""
    events: list[BusinessEvent] = []
    commitments: list[Commitment] = []
    for proposed in proposal.proposed_events:
        event = _upsert_event(session, message, conversation, proposed)
        events.append(event)
        if proposed.event_type == EventType.PAYMENT_COMMITMENT:
            commitments.append(_upsert_commitment(session, message, conversation, event, proposed))
    return AppliedAnalysis(events=events, commitments=commitments)


def _upsert_event(
    session: Session,
    message: Message,
    conversation: Conversation,
    proposed: ProposedEvent,
) -> BusinessEvent:
    existing = _find_event(session, message, proposed.event_type.value)
    if existing is not None:
        return existing

    event = BusinessEvent(
        business_id=message.business_id,
        event_type=proposed.event_type.value,
        customer_id=conversation.customer_id,
        conversation_id=conversation.id,
        source_message_id=message.id,
        confidence=proposed.confidence,
        urgency=proposed.urgency.value,
        extracted_data=_extracted_data(proposed),
        occurred_at=message.occurred_at,
    )
    try:
        with session.begin_nested():
            session.add(event)
            session.flush()
    except IntegrityError:
        found = _find_event(session, message, proposed.event_type.value)
        if found is None:
            raise
        return found
    return event


def _upsert_commitment(
    session: Session,
    message: Message,
    conversation: Conversation,
    event: BusinessEvent,
    proposed: ProposedEvent,
) -> Commitment:
    existing = _find_commitment(session, message)
    if existing is not None:
        return existing

    commitment = Commitment(
        business_id=message.business_id,
        customer_id=conversation.customer_id,
        source_event_id=event.id,
        source_message_id=message.id,
        commitment_type=CommitmentType.PAYMENT_COMMITMENT.value,
        owner_party=CommitmentOwner.CUSTOMER.value,
        description=proposed.description,
        due_at=proposed.due_at,
        due_text=proposed.due_text,
        due_precision=None if proposed.due_precision is None else proposed.due_precision.value,
        amount=proposed.amount,
        currency=proposed.currency,
        status=CommitmentStatus.PENDING.value,
    )
    try:
        with session.begin_nested():
            session.add(commitment)
            session.flush()
    except IntegrityError:
        found = _find_commitment(session, message)
        if found is None:
            raise
        return found
    return commitment


def _find_event(session: Session, message: Message, event_type: str) -> BusinessEvent | None:
    return session.scalar(
        select(BusinessEvent).where(
            BusinessEvent.business_id == message.business_id,
            BusinessEvent.source_message_id == message.id,
            BusinessEvent.event_type == event_type,
        )
    )


def _find_commitment(session: Session, message: Message) -> Commitment | None:
    return session.scalar(
        select(Commitment).where(
            Commitment.business_id == message.business_id,
            Commitment.source_message_id == message.id,
            Commitment.commitment_type == CommitmentType.PAYMENT_COMMITMENT.value,
        )
    )


def _extracted_data(proposed: ProposedEvent) -> dict[str, object]:
    data: dict[str, object] = {"description": proposed.description}
    if proposed.amount is not None and proposed.currency is not None:
        data["amount"] = format(proposed.amount, "f")
        data["currency"] = proposed.currency
    if proposed.due_text is not None:
        data["due_text"] = proposed.due_text
    if proposed.due_at is not None:
        data["due_at"] = proposed.due_at.isoformat()
    if proposed.event_type == EventType.PAYMENT_CLAIM:
        data["payment_verified"] = False
    return data
