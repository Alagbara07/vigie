import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.errors import ConflictError, NotFoundError
from app.models import Business, Conversation, Customer, Message
from app.schemas.inbox import (
    BusinessCreate,
    ConversationCreate,
    CustomerCreate,
    MessageCreate,
)

_SLUG_BREAKS = re.compile(r"[^a-z0-9]+")


def create_business(session: Session, payload: BusinessCreate) -> Business:
    business = Business(
        name=payload.name.strip(),
        slug=payload.slug or slugify(payload.name),
        default_currency=payload.default_currency,
        timezone=payload.timezone,
    )
    session.add(business)
    _commit(session, "A business with this slug already exists.")
    return business


def list_businesses(session: Session) -> list[Business]:
    return list(session.scalars(select(Business).order_by(Business.created_at)))


def create_customer(session: Session, business_id: uuid.UUID, payload: CustomerCreate) -> Customer:
    _require_business(session, business_id)
    customer = Customer(
        business_id=business_id,
        name=payload.name.strip(),
        contact_identifier=payload.contact_identifier.strip(),
        status=payload.status.value,
    )
    session.add(customer)
    _commit(session, "A customer with this contact identifier already exists.")
    return customer


def list_customers(session: Session, business_id: uuid.UUID) -> list[Customer]:
    _require_business(session, business_id)
    statement = (
        select(Customer)
        .where(Customer.business_id == business_id)
        .order_by(Customer.created_at)
    )
    return list(session.scalars(statement))


def create_conversation(
    session: Session,
    business_id: uuid.UUID,
    payload: ConversationCreate,
) -> Conversation:
    _require_business(session, business_id)
    if payload.customer_id is not None:
        _require_customer(session, business_id, payload.customer_id)
    conversation = Conversation(
        business_id=business_id,
        customer_id=payload.customer_id,
        channel=payload.channel.value,
        external_ref=payload.external_ref,
        status=payload.status.value,
    )
    session.add(conversation)
    _commit(session, "A conversation with this external reference already exists.")
    return conversation


def list_conversations(session: Session, business_id: uuid.UUID) -> list[Conversation]:
    _require_business(session, business_id)
    statement = (
        select(Conversation)
        .where(Conversation.business_id == business_id)
        .order_by(Conversation.created_at)
    )
    return list(session.scalars(statement))


def create_message(
    session: Session,
    business_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: MessageCreate,
) -> Message:
    _require_conversation(session, business_id, conversation_id)
    message = Message(
        business_id=business_id,
        conversation_id=conversation_id,
        sender_type=payload.sender_type.value,
        sender_identifier=payload.sender_identifier,
        direction=payload.direction.value,
        content=payload.content,
        occurred_at=payload.occurred_at,
        message_metadata=payload.metadata,
    )
    session.add(message)
    _commit(session, "The message could not be stored.")
    return message


def list_messages(
    session: Session,
    business_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> list[Message]:
    _require_conversation(session, business_id, conversation_id)
    statement = (
        select(Message)
        .where(Message.business_id == business_id, Message.conversation_id == conversation_id)
        .order_by(Message.occurred_at, Message.created_at)
    )
    return list(session.scalars(statement))


def slugify(name: str) -> str:
    slug = _SLUG_BREAKS.sub("-", name.strip().lower()).strip("-")
    if not slug:
        raise ConflictError("Business name must contain a letter or number.")
    return slug[:200]


def _require_business(session: Session, business_id: uuid.UUID) -> Business:
    business = session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    return business


def _require_customer(session: Session, business_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None or customer.business_id != business_id:
        raise NotFoundError("Customer not found.")
    return customer


def _require_conversation(
    session: Session,
    business_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.business_id != business_id:
        raise NotFoundError("Conversation not found.")
    return conversation


def _commit(session: Session, conflict_message: str) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(conflict_message) from exc
