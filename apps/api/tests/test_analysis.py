import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.errors import InvalidProposalError, NotFoundError
from app.models import Business, BusinessEvent, Commitment, Conversation, Customer, Message, Signal
from app.services.analysis import analyze_stored_message
from app.seed.demo import GREETING_TEXT, PAYMENT_CLAIM_TEXT, PAYMENT_PROMISE_TEXT, UNANSWERED_REQUEST_TEXT

LAGOS = ZoneInfo("Africa/Lagos")
REFERENCE_TIME = datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS)
FRIDAY = datetime(2026, 9, 25, tzinfo=LAGOS).date()


class RawProvider:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    @property
    def name(self) -> str:
        return "heuristic"

    def analyze_message(self, request: object) -> dict[str, Any]:
        return self.raw


def test_payment_claim_is_not_a_verified_payment(db_session: Session) -> None:
    business, message = _thread(db_session, "claim-shop", PAYMENT_CLAIM_TEXT)

    result = analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME)

    assert result.provider == "heuristic"
    assert result.proposal.intent == "payment_claim"
    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_type == "PAYMENT_CLAIM"
    assert Decimal(str(event.extracted_data["amount"])) == Decimal("150000")
    assert event.extracted_data["currency"] == "NGN"
    assert event.extracted_data["payment_verified"] is False
    assert result.commitments == []
    assert _count(db_session, Commitment) == 0
    assert _count(db_session, Signal) == 0
    assert message.content == PAYMENT_CLAIM_TEXT


def test_payment_commitment_stays_pending(db_session: Session) -> None:
    business, message = _thread(db_session, "promise-shop", PAYMENT_PROMISE_TEXT)

    result = analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME)

    assert len(result.events) == 1
    assert result.events[0].event_type == "PAYMENT_COMMITMENT"
    assert len(result.commitments) == 1
    commitment = result.commitments[0]
    assert commitment.status == "PENDING"
    assert commitment.amount == Decimal("150000.00")
    assert commitment.currency == "NGN"
    assert commitment.due_text == "Friday"
    assert commitment.due_precision == "DATE"
    assert commitment.due_at is not None
    assert commitment.due_at.astimezone(LAGOS).date() == FRIDAY
    assert _count(db_session, Signal) == 0


def test_wholesale_question_is_a_request_and_not_a_signal(db_session: Session) -> None:
    business, message = _thread(db_session, "request-shop", UNANSWERED_REQUEST_TEXT)

    result = analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME)

    assert result.proposal.intent == "unanswered_request"
    assert len(result.events) == 1
    assert result.events[0].event_type == "UNANSWERED_REQUEST"
    assert result.commitments == []
    assert _count(db_session, Signal) == 0


def test_greeting_creates_nothing(db_session: Session) -> None:
    business, message = _thread(db_session, "greeting-shop", GREETING_TEXT)

    result = analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME)

    assert result.proposal.intent == "no_business_event"
    assert result.proposal.proposed_events == []
    assert result.events == []
    assert result.commitments == []
    assert _count(db_session, BusinessEvent) == 0
    assert _count(db_session, Commitment) == 0
    assert _count(db_session, Signal) == 0


def test_repeated_analysis_does_not_duplicate_records(db_session: Session) -> None:
    business, message = _thread(db_session, "repeat-shop", PAYMENT_PROMISE_TEXT)

    first = analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME)
    second = analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME)

    assert first.events[0].id == second.events[0].id
    assert first.commitments[0].id == second.commitments[0].id
    assert _count(db_session, BusinessEvent) == 1
    assert _count(db_session, Commitment) == 1


def test_malformed_provider_output_is_rejected(db_session: Session) -> None:
    business, message = _thread(db_session, "invalid-shop", PAYMENT_CLAIM_TEXT)
    provider = RawProvider(
        {
            "intent": "payment_claim",
            "confidence": "0.900",
            "entities": [],
            "proposed_events": [
                {
                    "event_type": "PAYMENT_CLAIM",
                    "confidence": "0.900",
                    "urgency": "HIGH",
                    "amount": "150000.00",
                    "currency": "NGN",
                    "description": "Customer claims payment.",
                    "payment_verified": True,
                }
            ],
            "reasoning": "Trying to mark the payment verified.",
            "provider": "heuristic",
        }
    )

    with pytest.raises(InvalidProposalError):
        analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME, provider)

    assert _count(db_session, BusinessEvent) == 0
    assert _count(db_session, Commitment) == 0


def test_signal_type_cannot_be_proposed_as_an_event(db_session: Session) -> None:
    business, message = _thread(db_session, "signal-shop", PAYMENT_PROMISE_TEXT)
    provider = RawProvider(
        {
            "intent": "overdue",
            "confidence": "0.900",
            "entities": [],
            "proposed_events": [
                {
                    "event_type": "OVERDUE_PAYMENT",
                    "confidence": "0.900",
                    "urgency": "HIGH",
                    "description": "This is a signal, not an event.",
                }
            ],
            "reasoning": "Trying to skip the evaluator.",
            "provider": "heuristic",
        }
    )

    with pytest.raises(InvalidProposalError):
        analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME, provider)

    assert _count(db_session, Signal) == 0
    assert _count(db_session, BusinessEvent) == 0


def test_wrong_business_context_is_rejected(db_session: Session) -> None:
    business, message = _thread(db_session, "owner-shop", PAYMENT_CLAIM_TEXT)
    other = Business(name="Other Shop", slug="other-shop", default_currency="NGN", timezone="Africa/Lagos")
    db_session.add(other)
    db_session.flush()

    with pytest.raises(NotFoundError):
        analyze_stored_message(db_session, message.id, other.id, REFERENCE_TIME)

    assert _count(db_session, BusinessEvent) == 0


def test_analyze_endpoint_returns_claim_and_replay(api_client: TestClient) -> None:
    business = api_client.post("/api/businesses", json={"name": "Adaeze API", "slug": "adaeze-api"}).json()
    customer = api_client.post(
        f"/api/businesses/{business['id']}/customers",
        json={"name": "Chinedu Okafor", "contact_identifier": "2348011111111"},
    ).json()
    conversation = api_client.post(
        f"/api/businesses/{business['id']}/conversations",
        json={"customer_id": customer["id"], "channel": "simulated"},
    ).json()
    message = api_client.post(
        f"/api/businesses/{business['id']}/conversations/{conversation['id']}/messages",
        json={
            "sender_type": "customer",
            "direction": "inbound",
            "content": PAYMENT_CLAIM_TEXT,
            "occurred_at": "2026-09-23T08:15:00Z",
        },
    ).json()
    payload = {"business_id": business["id"], "reference_time": "2026-09-24T09:00:00+01:00"}

    first = api_client.post(f"/api/messages/{message['id']}/analyze", json=payload)
    second = api_client.post(f"/api/messages/{message['id']}/analyze", json=payload)
    wrong_business = api_client.post(
        f"/api/messages/{message['id']}/analyze",
        json={"business_id": str(uuid.uuid4()), "reference_time": "2026-09-24T09:00:00+01:00"},
    )

    assert first.status_code == 200
    body = first.json()
    assert body["provider"] == "heuristic"
    assert body["proposal"]["intent"] == "payment_claim"
    assert body["events"][0]["event_type"] == "PAYMENT_CLAIM"
    assert body["events"][0]["extracted_data"]["payment_verified"] is False
    assert Decimal(body["events"][0]["extracted_data"]["amount"]) == Decimal("150000")
    assert body["commitments"] == []
    assert second.status_code == 200
    assert second.json()["events"][0]["id"] == body["events"][0]["id"]
    assert wrong_business.status_code == 404


def _thread(session: Session, slug: str, content: str) -> tuple[Business, Message]:
    business = Business(name=slug, slug=slug, default_currency="NGN", timezone="Africa/Lagos")
    session.add(business)
    session.flush()
    customer = Customer(
        business_id=business.id,
        name="Customer",
        contact_identifier=str(uuid.uuid4()),
        status="ACTIVE",
    )
    session.add(customer)
    session.flush()
    conversation = Conversation(
        business_id=business.id,
        customer_id=customer.id,
        channel="simulated",
        status="OPEN",
    )
    session.add(conversation)
    session.flush()
    message = Message(
        business_id=business.id,
        conversation_id=conversation.id,
        sender_type="customer",
        direction="inbound",
        content=content,
        occurred_at=datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
    )
    session.add(message)
    session.flush()
    return business, message


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)
