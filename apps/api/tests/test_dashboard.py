import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Business, BusinessEvent, Commitment, Conversation, Customer, Message, Signal
from app.seed.demo import PAYMENT_PROMISE_TEXT


def test_summary_counts_open_risk_and_ignores_closed_money(api_client: TestClient, db_session: Session) -> None:
    business, signal = _overdue_signal(db_session, "summary-shop")
    other = _signal(
        business,
        signal_type="UNANSWERED_REQUEST",
        category="OPERATIONS",
        severity="MEDIUM",
        title="Unanswered request",
        amount=None,
        currency=None,
    )
    closed = _signal(
        business,
        signal_type="OVERDUE_PAYMENT",
        category="REVENUE",
        severity="HIGH",
        title="Old overdue",
        amount=Decimal("50000.00"),
        currency="NGN",
        status="RESOLVED",
        commitment_id=None,
        event_id=None,
        customer_id=signal.customer_id,
    )
    foreign_currency = _signal(
        business,
        signal_type="OVERDUE_PAYMENT",
        category="REVENUE",
        severity="HIGH",
        title="Dollar overdue",
        amount=Decimal("20.00"),
        currency="USD",
        commitment_id=None,
        event_id=None,
        customer_id=signal.customer_id,
    )
    db_session.add_all([other, closed, foreign_currency])
    db_session.flush()

    response = api_client.get("/api/dashboard/summary", params={"business_id": str(business.id)})
    listed = api_client.get("/api/signals", params={"business_id": str(business.id)})

    assert response.status_code == 200
    body = response.json()
    assert body["business_name"] == "summary-shop"
    assert body["currency"] == "NGN"
    assert body["open_signals"] == 3
    assert body["high_priority_signals"] == 2
    assert Decimal(body["revenue_at_risk"]) == Decimal("150000.00")
    assert body["missed_commitments"] == 1
    assert body["opportunity_signals"] == 0
    assert body["recent_conversations"][0]["last_message"] == PAYMENT_PROMISE_TEXT
    assert body["recent_conversations"][0]["customer_name"] == "Amaka Bello"
    groups = {item["title"]: item["attention_group"] for item in listed.json()}
    assert groups["Payment overdue"] == "risk"
    assert groups["Unanswered request"] == "operations"


def test_signal_detail_includes_evidence_and_commitment(api_client: TestClient, db_session: Session) -> None:
    business, signal = _overdue_signal(db_session, "detail-shop")

    response = api_client.get(f"/api/signals/{signal.id}", params={"business_id": str(business.id)})
    wrong = api_client.get(f"/api/signals/{signal.id}", params={"business_id": str(uuid.uuid4())})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(signal.id)
    assert body["customer"]["name"] == "Amaka Bello"
    assert body["commitment"]["status"] == "MISSED"
    assert Decimal(body["commitment"]["amount"]) == Decimal("150000.00")
    assert body["commitment"]["due_text"] == "Friday"
    assert body["event"]["event_type"] == "PAYMENT_COMMITMENT"
    assert body["evidence"]["content"] == PAYMENT_PROMISE_TEXT
    assert body["evidence"]["sender_type"] == "customer"
    assert body["conversation"]["message_count"] == 1
    assert body["action"] is None
    assert wrong.status_code == 404


def test_empty_business_summary_is_zero(api_client: TestClient) -> None:
    business = api_client.post("/api/businesses", json={"name": "Quiet Shop", "slug": "quiet-shop"}).json()

    response = api_client.get("/api/dashboard/summary", params={"business_id": business["id"]})
    missing = api_client.get("/api/dashboard/summary", params={"business_id": str(uuid.uuid4())})

    assert response.status_code == 200
    body = response.json()
    assert body["open_signals"] == 0
    assert body["high_priority_signals"] == 0
    assert Decimal(body["revenue_at_risk"]) == Decimal("0")
    assert body["missed_commitments"] == 0
    assert body["recent_conversations"] == []
    assert missing.status_code == 404


def test_summary_does_not_include_another_business(api_client: TestClient, db_session: Session) -> None:
    owner, _signal = _overdue_signal(db_session, "owner-summary")
    other = api_client.post("/api/businesses", json={"name": "Other Summary", "slug": "other-summary"}).json()

    response = api_client.get("/api/dashboard/summary", params={"business_id": other["id"]})

    assert response.status_code == 200
    assert response.json()["open_signals"] == 0
    assert response.json()["revenue_at_risk"] == "0.00" or Decimal(response.json()["revenue_at_risk"]) == Decimal("0")
    assert owner.id != uuid.UUID(other["id"])


def _overdue_signal(session: Session, slug: str) -> tuple[Business, Signal]:
    business = Business(name=slug, slug=slug, default_currency="NGN", timezone="Africa/Lagos")
    session.add(business)
    session.flush()
    customer = Customer(
        business_id=business.id,
        name="Amaka Bello",
        contact_identifier=f"{slug}-customer",
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
        content=PAYMENT_PROMISE_TEXT,
        occurred_at=datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
    )
    session.add(message)
    session.flush()
    event = BusinessEvent(
        business_id=business.id,
        event_type="PAYMENT_COMMITMENT",
        customer_id=customer.id,
        conversation_id=conversation.id,
        source_message_id=message.id,
        confidence=Decimal("0.880"),
        urgency="MEDIUM",
        extracted_data={"description": "Customer promised to pay NGN 150000 on Friday."},
        occurred_at=message.occurred_at,
    )
    session.add(event)
    session.flush()
    commitment = Commitment(
        business_id=business.id,
        customer_id=customer.id,
        source_event_id=event.id,
        source_message_id=message.id,
        commitment_type="PAYMENT_COMMITMENT",
        owner_party="CUSTOMER",
        description="Customer promised to pay NGN 150000 on Friday.",
        due_at=datetime(2026, 9, 25, 0, 0, tzinfo=timezone.utc),
        due_text="Friday",
        due_precision="DATE",
        amount=Decimal("150000.00"),
        currency="NGN",
        status="MISSED",
    )
    session.add(commitment)
    session.flush()
    signal = _signal(
        business,
        signal_type="OVERDUE_PAYMENT",
        category="REVENUE",
        severity="HIGH",
        title="Payment overdue",
        amount=Decimal("150000.00"),
        currency="NGN",
        customer_id=customer.id,
        commitment_id=commitment.id,
        event_id=event.id,
        description="Amaka Bello promised NGN 150000 by Friday. The commitment has not been fulfilled.",
    )
    session.add(signal)
    session.flush()
    return business, signal


def _signal(
    business: Business,
    *,
    signal_type: str,
    category: str,
    severity: str,
    title: str,
    amount: Decimal | None,
    currency: str | None,
    status: str = "OPEN",
    customer_id: uuid.UUID | None = None,
    commitment_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    description: str = "Needs attention.",
) -> Signal:
    return Signal(
        business_id=business.id,
        signal_type=signal_type,
        category=category,
        severity=severity,
        title=title,
        description=description,
        status=status,
        confidence=Decimal("1.000"),
        financial_impact_amount=amount,
        currency=currency,
        event_id=event_id,
        customer_id=customer_id,
        commitment_id=commitment_id,
    )
