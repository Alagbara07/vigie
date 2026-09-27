import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.attention import classify_attention
from app.integrations.messages import describe_source
from app.domain.enums import Severity, SignalCategory, SignalStatus, SignalType
from app.domain.errors import NotFoundError
from app.models import Action, Business, BusinessEvent, Commitment, Conversation, Customer, Message, Signal
from app.schemas.signals import (
    ActionBrief,
    CommitmentBrief,
    ConversationBrief,
    CustomerBrief,
    EventBrief,
    EvidenceRead,
    SignalDetailRead,
    SignalListRead,
    SignalRead,
)


def list_signals(
    session: Session,
    business_id: uuid.UUID,
    *,
    status: SignalStatus | None = None,
    signal_type: SignalType | None = None,
    category: SignalCategory | None = None,
    severity: Severity | None = None,
) -> list[Signal]:
    business = session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    statement = select(Signal).where(Signal.business_id == business.id)
    if status is not None:
        statement = statement.where(Signal.status == status.value)
    if signal_type is not None:
        statement = statement.where(Signal.signal_type == signal_type.value)
    if category is not None:
        statement = statement.where(Signal.category == category.value)
    if severity is not None:
        statement = statement.where(Signal.severity == severity.value)
    statement = statement.order_by(Signal.created_at.asc(), Signal.id.asc())
    return list(session.scalars(statement).all())


def list_signal_reads(
    session: Session,
    business_id: uuid.UUID,
    *,
    status: SignalStatus | None = None,
    signal_type: SignalType | None = None,
    category: SignalCategory | None = None,
    severity: Severity | None = None,
) -> list[SignalListRead]:
    signals = list_signals(
        session,
        business_id,
        status=status,
        signal_type=signal_type,
        category=category,
        severity=severity,
    )
    names = _customer_names(session, business_id, signals)
    actions = _actions_by_signal(session, business_id, [signal.id for signal in signals])
    return [
        SignalListRead(
            **_signal_read(signal, names.get(signal.customer_id) if signal.customer_id else None).model_dump(),
            action=_action_brief(actions.get(signal.id)),
        )
        for signal in signals
    ]


def get_signal(session: Session, signal_id: uuid.UUID, business_id: uuid.UUID) -> Signal:
    signal = session.get(Signal, signal_id)
    if signal is None or signal.business_id != business_id:
        raise NotFoundError("Signal not found.")
    return signal


def get_signal_detail(session: Session, signal_id: uuid.UUID, business_id: uuid.UUID) -> SignalDetailRead:
    signal = get_signal(session, signal_id, business_id)
    business = session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    customer = _same_business(session.get(Customer, signal.customer_id), business_id) if signal.customer_id else None
    commitment = (
        _same_business(session.get(Commitment, signal.commitment_id), business_id) if signal.commitment_id else None
    )
    event = _same_business(session.get(BusinessEvent, signal.event_id), business_id) if signal.event_id else None
    message = _evidence_message(session, business_id, event, commitment)
    conversation = _conversation_for(session, business_id, event, message)
    action = session.scalar(
        select(Action).where(Action.business_id == business_id, Action.signal_id == signal.id)
    )
    base = _signal_read(signal, customer.name if customer is not None else None)
    return SignalDetailRead(
        **base.model_dump(),
        timezone=business.timezone,
        customer=None
        if customer is None
        else CustomerBrief(
            id=customer.id,
            name=customer.name,
            status=customer.status,
            created_at=customer.created_at,
        ),
        commitment=None
        if commitment is None
        else CommitmentBrief(
            id=commitment.id,
            commitment_type=commitment.commitment_type,
            status=commitment.status,
            amount=commitment.amount,
            currency=commitment.currency,
            due_at=commitment.due_at,
            due_text=commitment.due_text,
            description=commitment.description,
        ),
        event=None if event is None else _event_brief(event),
        evidence=None if message is None else _evidence_read(message),
        conversation=None if conversation is None else _conversation_brief(session, business_id, conversation),
        action=_action_brief(action),
    )


def _signal_read(signal: Signal, customer_name: str | None) -> SignalRead:
    return SignalRead(
        id=signal.id,
        business_id=signal.business_id,
        signal_type=signal.signal_type,
        category=signal.category,
        severity=signal.severity,
        title=signal.title,
        description=signal.description,
        status=signal.status,
        confidence=signal.confidence,
        financial_impact_amount=signal.financial_impact_amount,
        currency=signal.currency,
        event_id=signal.event_id,
        customer_id=signal.customer_id,
        commitment_id=signal.commitment_id,
        created_at=signal.created_at,
        customer_name=customer_name,
        attention_group=classify_attention(signal.signal_type, signal.category),
    )


def _customer_names(
    session: Session,
    business_id: uuid.UUID,
    signals: Sequence[Signal],
) -> dict[uuid.UUID, str]:
    customer_ids = {signal.customer_id for signal in signals if signal.customer_id is not None}
    if not customer_ids:
        return {}
    rows = session.scalars(
        select(Customer).where(Customer.business_id == business_id, Customer.id.in_(customer_ids))
    ).all()
    return {customer.id: customer.name for customer in rows}


def _same_business(record: object, business_id: uuid.UUID) -> object | None:
    if record is None or getattr(record, "business_id", None) != business_id:
        return None
    return record


def _evidence_message(
    session: Session,
    business_id: uuid.UUID,
    event: BusinessEvent | None,
    commitment: Commitment | None,
) -> Message | None:
    message_id = None
    if event is not None:
        message_id = event.source_message_id
    elif commitment is not None:
        message_id = commitment.source_message_id
    if message_id is None:
        return None
    message = session.get(Message, message_id)
    if message is None or message.business_id != business_id:
        return None
    return message


def _conversation_for(
    session: Session,
    business_id: uuid.UUID,
    event: BusinessEvent | None,
    message: Message | None,
) -> Conversation | None:
    conversation_id = None
    if event is not None and event.conversation_id is not None:
        conversation_id = event.conversation_id
    elif message is not None:
        conversation_id = message.conversation_id
    if conversation_id is None:
        return None
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.business_id != business_id:
        return None
    return conversation


def _evidence_read(message: Message) -> EvidenceRead:
    label, connection = describe_source(message.source)
    return EvidenceRead(
        message_id=message.id,
        content=message.content,
        sender_type=message.sender_type,
        direction=message.direction,
        occurred_at=message.occurred_at,
        source=message.source,
        source_label=label,
        connection=connection,
        external_message_id=message.external_message_id,
    )


def _event_brief(event: BusinessEvent) -> EventBrief:
    description = None
    if isinstance(event.extracted_data, dict):
        raw = event.extracted_data.get("description")
        if isinstance(raw, str) and raw.strip():
            description = raw.strip()
    return EventBrief(
        id=event.id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        description=description,
    )


def _conversation_brief(session: Session, business_id: uuid.UUID, conversation: Conversation) -> ConversationBrief:
    message_count = int(
        session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.business_id == business_id, Message.conversation_id == conversation.id)
        )
        or 0
    )
    return ConversationBrief(id=conversation.id, channel=conversation.channel, message_count=message_count)


def _actions_by_signal(session: Session, business_id: uuid.UUID, signal_ids: list[uuid.UUID]) -> dict[uuid.UUID, Action]:
    if not signal_ids:
        return {}
    rows = session.scalars(
        select(Action).where(Action.business_id == business_id, Action.signal_id.in_(signal_ids))
    ).all()
    grouped: dict[uuid.UUID, list[Action]] = {}
    for row in rows:
        grouped.setdefault(row.signal_id, []).append(row)
    return {signal_id: _preferred_action(group) for signal_id, group in grouped.items()}


def _preferred_action(actions: list[Action]) -> Action:
    proposed = [action for action in actions if action.status == "PROPOSED"]
    pool = proposed or actions
    return min(pool, key=lambda action: (action.created_at, str(action.id)))


def _action_brief(action: Action | None) -> ActionBrief | None:
    if action is None:
        return None
    return ActionBrief(
        id=action.id,
        action_type=action.action_type,
        title=action.title,
        description=action.description,
        status=action.status,
        proposed_content=action.proposed_content,
    )
