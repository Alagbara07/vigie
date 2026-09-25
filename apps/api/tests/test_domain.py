import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Action, Business, BusinessEvent, Commitment, Conversation, Customer, Message, Signal


def test_event_type_is_extensible_text(engine) -> None:
    with engine.connect() as connection:
        data_type = connection.execute(
            text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'business_events' AND column_name = 'event_type'
                """
            )
        ).scalar_one()
    assert data_type == "character varying"
    assert "payments" not in inspect(engine).get_table_names()


def test_customer_conversation_and_message_belong_to_one_business(db_session: Session) -> None:
    business = _business(db_session, "adaeze-wears")
    customer = _customer(db_session, business)
    conversation = _conversation(db_session, business, customer)
    message = _message(db_session, business, conversation, "Good morning.")

    assert customer.business_id == business.id
    assert conversation.business_id == business.id
    assert conversation.customer_id == customer.id
    assert message.business_id == business.id
    assert message.conversation_id == conversation.id
    assert message.content == "Good morning."


def test_conversation_cannot_use_another_business_customer(db_session: Session) -> None:
    first = _business(db_session, "first-business")
    second = _business(db_session, "second-business")
    outsider = _customer(db_session, second)
    conversation = Conversation(
        business_id=first.id,
        customer_id=outsider.id,
        channel="simulated",
        status="OPEN",
    )
    db_session.add(conversation)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_message_cannot_point_at_another_business_conversation(db_session: Session) -> None:
    first = _business(db_session, "message-owner")
    second = _business(db_session, "message-other")
    conversation = _conversation(db_session, first, _customer(db_session, first))
    message = Message(
        business_id=second.id,
        conversation_id=conversation.id,
        sender_type="customer",
        direction="inbound",
        content="Hello",
        occurred_at=_now(),
    )
    db_session.add(message)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_event_requires_source_message_and_stays_separate_from_signal(db_session: Session) -> None:
    business = _business(db_session, "event-business")
    customer = _customer(db_session, business)
    conversation = _conversation(db_session, business, customer)
    message = _message(
        db_session,
        business,
        conversation,
        "I sent the ₦150,000 balance yesterday. Please confirm.",
    )
    event = BusinessEvent(
        business_id=business.id,
        event_type="PAYMENT_CLAIM",
        customer_id=customer.id,
        conversation_id=conversation.id,
        source_message_id=message.id,
        confidence=Decimal("0.910"),
        urgency="HIGH",
        extracted_data={"amount": "150000.00", "currency": "NGN", "payment_verified": False},
        occurred_at=message.occurred_at,
    )
    db_session.add(event)
    db_session.flush()

    assert event.source_message_id == message.id
    assert db_session.query(Signal).count() == 0
    assert message.content.startswith("I sent the")


def test_event_cannot_cite_another_business_message(db_session: Session) -> None:
    owner = _business(db_session, "event-owner")
    other = _business(db_session, "event-other")
    message = _message(
        db_session,
        owner,
        _conversation(db_session, owner, _customer(db_session, owner)),
        "Please confirm the transfer.",
    )
    event = BusinessEvent(
        business_id=other.id,
        event_type="PAYMENT_CLAIM",
        source_message_id=message.id,
        confidence=Decimal("0.800"),
        urgency="HIGH",
        extracted_data={},
        occurred_at=message.occurred_at,
    )
    db_session.add(event)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_commitment_references_message_and_event_without_becoming_a_signal(db_session: Session) -> None:
    business = _business(db_session, "commitment-business")
    customer = _customer(db_session, business)
    conversation = _conversation(db_session, business, customer)
    message = _message(db_session, business, conversation, "I'll pay the remaining ₦150,000 on Friday.")
    event = BusinessEvent(
        business_id=business.id,
        event_type="PAYMENT_COMMITMENT",
        customer_id=customer.id,
        conversation_id=conversation.id,
        source_message_id=message.id,
        confidence=Decimal("0.870"),
        urgency="MEDIUM",
        extracted_data={"due_text": "Friday"},
        occurred_at=message.occurred_at,
    )
    db_session.add(event)
    db_session.flush()
    commitment = Commitment(
        business_id=business.id,
        customer_id=customer.id,
        source_event_id=event.id,
        source_message_id=message.id,
        commitment_type="PAYMENT_COMMITMENT",
        owner_party="CUSTOMER",
        description="Customer promised the remaining balance on Friday.",
        due_text="Friday",
        due_precision="AMBIGUOUS",
        amount=Decimal("150000.00"),
        currency="NGN",
        status="PENDING",
    )
    db_session.add(commitment)
    db_session.flush()

    assert commitment.source_message_id == message.id
    assert commitment.source_event_id == event.id
    assert commitment.status == "PENDING"
    assert commitment.due_at is None
    assert db_session.query(Signal).count() == 0


def test_duplicate_open_overdue_signal_for_one_commitment_is_rejected(db_session: Session) -> None:
    business = _business(db_session, "signal-business")
    customer = _customer(db_session, business)
    message = _message(
        db_session,
        business,
        _conversation(db_session, business, customer),
        "I'll pay on Friday.",
    )
    commitment = Commitment(
        business_id=business.id,
        customer_id=customer.id,
        source_message_id=message.id,
        commitment_type="PAYMENT_COMMITMENT",
        owner_party="CUSTOMER",
        description="Friday payment.",
        due_text="Friday",
        due_precision="AMBIGUOUS",
        amount=Decimal("150000.00"),
        currency="NGN",
        status="MISSED",
    )
    db_session.add(commitment)
    db_session.flush()
    db_session.add(_overdue_signal(business, customer, commitment))
    db_session.flush()
    db_session.add(_overdue_signal(business, customer, commitment))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_action_references_signal_and_is_not_created_with_it(db_session: Session) -> None:
    business = _business(db_session, "action-business")
    customer = _customer(db_session, business)
    message = _message(
        db_session,
        business,
        _conversation(db_session, business, customer),
        "I'll pay on Friday.",
    )
    commitment = Commitment(
        business_id=business.id,
        customer_id=customer.id,
        source_message_id=message.id,
        commitment_type="PAYMENT_COMMITMENT",
        owner_party="CUSTOMER",
        description="Friday payment.",
        amount=Decimal("150000.00"),
        currency="NGN",
        status="MISSED",
    )
    db_session.add(commitment)
    db_session.flush()
    signal = _overdue_signal(business, customer, commitment)
    db_session.add(signal)
    db_session.flush()

    assert db_session.query(Action).count() == 0

    action = Action(
        business_id=business.id,
        signal_id=signal.id,
        action_type="VERIFY_PAYMENT",
        status="PROPOSED",
        proposed_content="Ask for the transfer receipt before dispatch.",
    )
    db_session.add(action)
    db_session.flush()

    assert action.signal_id == signal.id
    assert action.approved_at is None
    assert action.executed_at is None


def test_confidence_above_one_is_rejected(db_session: Session) -> None:
    business = _business(db_session, "confidence-business")
    customer = _customer(db_session, business)
    message = _message(
        db_session,
        business,
        _conversation(db_session, business, customer),
        "Checking confidence.",
    )
    event = BusinessEvent(
        business_id=business.id,
        event_type="PAYMENT_CLAIM",
        source_message_id=message.id,
        confidence=Decimal("1.500"),
        urgency="HIGH",
        extracted_data={},
        occurred_at=message.occurred_at,
    )
    db_session.add(event)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_commitment_status_must_be_a_known_state(db_session: Session) -> None:
    business = _business(db_session, "status-business")
    message = _message(
        db_session,
        business,
        _conversation(db_session, business, _customer(db_session, business)),
        "Checking status.",
    )
    commitment = Commitment(
        business_id=business.id,
        source_message_id=message.id,
        commitment_type="PAYMENT_COMMITMENT",
        owner_party="CUSTOMER",
        description="Invalid status.",
        status="VERIFIED",
    )
    db_session.add(commitment)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def _business(session: Session, slug: str) -> Business:
    business = Business(name=slug, slug=slug, default_currency="NGN", timezone="Africa/Lagos")
    session.add(business)
    session.flush()
    return business


def _customer(session: Session, business: Business, contact: str | None = None) -> Customer:
    customer = Customer(
        business_id=business.id,
        name="Customer",
        contact_identifier=contact or str(uuid.uuid4()),
        status="ACTIVE",
    )
    session.add(customer)
    session.flush()
    return customer


def _conversation(session: Session, business: Business, customer: Customer) -> Conversation:
    conversation = Conversation(
        business_id=business.id,
        customer_id=customer.id,
        channel="simulated",
        status="OPEN",
    )
    session.add(conversation)
    session.flush()
    return conversation


def _message(session: Session, business: Business, conversation: Conversation, content: str) -> Message:
    message = Message(
        business_id=business.id,
        conversation_id=conversation.id,
        sender_type="customer",
        direction="inbound",
        content=content,
        occurred_at=_now(),
    )
    session.add(message)
    session.flush()
    return message


def _overdue_signal(business: Business, customer: Customer, commitment: Commitment) -> Signal:
    return Signal(
        business_id=business.id,
        signal_type="OVERDUE_PAYMENT",
        category="RISK",
        severity="HIGH",
        title="Payment overdue",
        description="The promised payment was not fulfilled.",
        status="OPEN",
        confidence=Decimal("0.900"),
        financial_impact_amount=Decimal("150000.00"),
        currency="NGN",
        customer_id=customer.id,
        commitment_id=commitment.id,
    )


def _now() -> datetime:
    return datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
