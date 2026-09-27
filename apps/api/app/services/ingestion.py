import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import Channel, ConversationStatus, CustomerStatus, Direction, MessageSource
from app.domain.errors import NotFoundError
from app.integrations.messages import NormalizedMessage
from app.models import Business, BusinessEvent, Conversation, Customer, Message


@dataclass(frozen=True)
class IngestResult:
    message: Message
    created: bool
    customer_name: str


def ingest_message(session: Session, incoming: NormalizedMessage) -> IngestResult:
    """Store one outside message. Interpretation stays in the analysis service."""
    business = session.get(Business, incoming.business_id)
    if business is None:
        raise NotFoundError("Business not found.")

    existing = _existing_message(session, incoming)
    if existing is not None:
        return IngestResult(message=existing, created=False, customer_name=_customer_name(session, existing))

    customer = _customer(session, incoming)
    conversation = _conversation(session, incoming, customer)
    message = Message(
        business_id=incoming.business_id,
        conversation_id=conversation.id,
        sender_type=incoming.sender_type.value,
        sender_identifier=incoming.sender_identifier or incoming.customer_name,
        direction=Direction.INBOUND.value,
        content=incoming.text,
        occurred_at=incoming.timestamp,
        source=incoming.source.value,
        external_message_id=incoming.external_message_id,
        message_metadata=incoming.metadata,
    )
    session.add(message)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _existing_message(session, incoming)
        if existing is None:
            raise
        return IngestResult(message=existing, created=False, customer_name=_customer_name(session, existing))
    return IngestResult(message=message, created=True, customer_name=customer.name)


def list_demo_messages(session: Session, business_id: uuid.UUID) -> list[tuple[Message, str, list[str]]]:
    business = session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    rows = session.execute(
        select(Message, Customer.name)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(Message.business_id == business_id, Message.source == MessageSource.DEMO.value)
        .order_by(Message.occurred_at.desc(), Message.created_at.desc())
        .limit(8)
    ).all()
    return [(message, name, _event_types(session, message)) for message, name in rows]


def event_types_for(session: Session, message: Message) -> list[str]:
    return _event_types(session, message)


def _existing_message(session: Session, incoming: NormalizedMessage) -> Message | None:
    return session.scalar(
        select(Message).where(
            Message.business_id == incoming.business_id,
            Message.source == incoming.source.value,
            Message.external_message_id == incoming.external_message_id,
        )
    )


def _customer(session: Session, incoming: NormalizedMessage) -> Customer:
    contact = _contact(incoming)
    customer = session.scalar(
        select(Customer).where(
            Customer.business_id == incoming.business_id,
            Customer.contact_identifier == contact,
        )
    )
    if customer is not None:
        return customer
    customer = Customer(
        business_id=incoming.business_id,
        name=incoming.customer_name,
        contact_identifier=contact,
        status=CustomerStatus.ACTIVE.value,
    )
    session.add(customer)
    session.flush()
    return customer


def _conversation(session: Session, incoming: NormalizedMessage, customer: Customer) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.business_id == incoming.business_id,
            Conversation.external_ref == incoming.external_conversation_id,
        )
    )
    if conversation is not None:
        return conversation
    conversation = Conversation(
        business_id=incoming.business_id,
        customer_id=customer.id,
        channel=_channel(incoming.source).value,
        external_ref=incoming.external_conversation_id,
        status=ConversationStatus.OPEN.value,
    )
    session.add(conversation)
    session.flush()
    return conversation


_CHANNEL_FOR_SOURCE = {
    MessageSource.WHATSAPP: Channel.WHATSAPP,
    MessageSource.GMAIL: Channel.EMAIL,
    MessageSource.MICROSOFT365: Channel.EMAIL,
    MessageSource.DEMO: Channel.DEMO,
}


def _channel(source: MessageSource) -> Channel:
    return _CHANNEL_FOR_SOURCE[source]


def _contact(incoming: NormalizedMessage) -> str:
    identity = incoming.external_customer_id or incoming.customer_name.casefold()
    return f"{incoming.source.value}:{identity}"[:200]


def _customer_name(session: Session, message: Message) -> str:
    conversation = session.get(Conversation, message.conversation_id)
    if conversation is None or conversation.customer_id is None:
        return message.sender_identifier or "Customer"
    customer = session.get(Customer, conversation.customer_id)
    if customer is None:
        return message.sender_identifier or "Customer"
    return customer.name


def _event_types(session: Session, message: Message) -> list[str]:
    rows = session.scalars(
        select(BusinessEvent.event_type).where(
            BusinessEvent.business_id == message.business_id,
            BusinessEvent.source_message_id == message.id,
        )
    ).all()
    return list(rows)
