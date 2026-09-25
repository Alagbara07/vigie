import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Business, Conversation, Customer, Message

logger = logging.getLogger(__name__)

DEMO_SLUG = "adaeze-wears"
DEMO_NAME = "Adaeze Wears"

PAYMENT_CLAIM_TEXT = "I sent the ₦150,000 balance yesterday. Please confirm."
PAYMENT_PROMISE_TEXT = "I'll pay the remaining ₦150,000 on Friday."
GREETING_TEXT = "Good morning."
UNANSWERED_REQUEST_TEXT = "How much is the wholesale price for 100 units?"


def seed_demo(session: Session) -> int:
    """Insert the demo conversations. Existing rows are left unchanged.

    Messages are stored as written. This does not create events, commitments,
    signals, or payments.
    """
    business = session.scalar(select(Business).where(Business.slug == DEMO_SLUG))
    if business is None:
        business = Business(
            id=_id("business"),
            name=DEMO_NAME,
            slug=DEMO_SLUG,
            default_currency="NGN",
            timezone="Africa/Lagos",
        )
        session.add(business)
        session.flush()
        logger.info("Created demo business %s", business.slug)

    created = 0
    for scenario in _scenarios():
        exists = session.scalar(
            select(Conversation.id).where(
                Conversation.business_id == business.id,
                Conversation.external_ref == scenario["external_ref"],
            )
        )
        if exists is not None:
            continue
        customer = Customer(
            id=scenario["customer_id"],
            business_id=business.id,
            name=scenario["customer_name"],
            contact_identifier=scenario["contact_identifier"],
            status="ACTIVE",
        )
        conversation = Conversation(
            id=scenario["conversation_id"],
            business_id=business.id,
            customer_id=customer.id,
            channel="simulated",
            external_ref=scenario["external_ref"],
            status="OPEN",
        )
        message = Message(
            id=scenario["message_id"],
            business_id=business.id,
            conversation_id=conversation.id,
            sender_type="customer",
            sender_identifier=scenario["contact_identifier"],
            direction="inbound",
            content=scenario["content"],
            occurred_at=scenario["occurred_at"],
        )
        session.add(customer)
        session.flush()
        session.add(conversation)
        session.flush()
        session.add(message)
        session.flush()
        created += 1
        logger.info("Seeded conversation %s", scenario["external_ref"])
    return created


def _id(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.UUID("6f0d7c4e-1a2b-4c3d-9e8f-0a1b2c3d4e5f"), name)


def _scenarios() -> tuple[dict, ...]:
    return (
        {
            "external_ref": "seed-payment-claim",
            "customer_id": _id("customer-payment-claim"),
            "customer_name": "Chinedu Okafor",
            "contact_identifier": "2348010000001",
            "conversation_id": _id("conversation-payment-claim"),
            "message_id": _id("message-payment-claim"),
            "content": PAYMENT_CLAIM_TEXT,
            "occurred_at": datetime(2026, 9, 23, 8, 15, tzinfo=timezone.utc),
        },
        {
            "external_ref": "seed-payment-promise",
            "customer_id": _id("customer-payment-promise"),
            "customer_name": "Amaka Bello",
            "contact_identifier": "2348010000002",
            "conversation_id": _id("conversation-payment-promise"),
            "message_id": _id("message-payment-promise"),
            "content": PAYMENT_PROMISE_TEXT,
            "occurred_at": datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
        },
        {
            "external_ref": "seed-greeting",
            "customer_id": _id("customer-greeting"),
            "customer_name": "Tunde Adeyemi",
            "contact_identifier": "2348010000003",
            "conversation_id": _id("conversation-greeting"),
            "message_id": _id("message-greeting"),
            "content": GREETING_TEXT,
            "occurred_at": datetime(2026, 9, 24, 6, 5, tzinfo=timezone.utc),
        },
        {
            "external_ref": "seed-unanswered-request",
            "customer_id": _id("customer-unanswered-request"),
            "customer_name": "Ngozi Eze",
            "contact_identifier": "2348010000004",
            "conversation_id": _id("conversation-unanswered-request"),
            "message_id": _id("message-unanswered-request"),
            "content": UNANSWERED_REQUEST_TEXT,
            "occurred_at": datetime(2026, 9, 24, 7, 30, tzinfo=timezone.utc),
        },
    )
