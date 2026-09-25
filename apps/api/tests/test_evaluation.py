import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import DuePrecision
from app.domain.errors import NotFoundError
from app.evaluators.time import is_past_due
from app.models import Business, BusinessEvent, Commitment, Conversation, Customer, Message, Signal
from app.seed.demo import (
    GREETING_TEXT,
    PAYMENT_CLAIM_TEXT,
    PAYMENT_PROMISE_TEXT,
    UNANSWERED_REQUEST_TEXT,
    seed_demo,
)
from app.services.analysis import analyze_stored_message
from app.services.evaluation import run_evaluation

LAGOS = ZoneInfo("Africa/Lagos")
BEFORE_DUE = datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS)
DUE_START = datetime(2026, 9, 25, 0, 0, tzinfo=LAGOS)
DUE_AFTERNOON = datetime(2026, 9, 25, 9, 0, tzinfo=LAGOS)
DUE_EVENING = datetime(2026, 9, 25, 23, 59, tzinfo=LAGOS)
NEXT_LOCAL_DAY = datetime(2026, 9, 26, 0, 0, tzinfo=LAGOS)
AFTER_DUE = datetime(2026, 9, 26, 9, 0, tzinfo=LAGOS)


def test_date_commitment_stays_pending_through_the_due_day() -> None:
    assert is_past_due(DUE_START, DuePrecision.DATE.value, BEFORE_DUE, "Africa/Lagos") is False
    assert is_past_due(DUE_START, DuePrecision.DATE.value, DUE_START, "Africa/Lagos") is False
    assert is_past_due(DUE_START, DuePrecision.DATE.value, DUE_AFTERNOON, "Africa/Lagos") is False
    assert is_past_due(DUE_START, DuePrecision.DATE.value, DUE_EVENING, "Africa/Lagos") is False
    assert is_past_due(DUE_START, DuePrecision.DATE.value, NEXT_LOCAL_DAY, "Africa/Lagos") is True
    assert is_past_due(DUE_START, DuePrecision.DATE.value, AFTER_DUE, "Africa/Lagos") is True


def test_exact_commitment_is_missed_only_after_the_instant() -> None:
    due = datetime(2026, 9, 25, 15, 0, tzinfo=LAGOS)
    assert is_past_due(due, DuePrecision.EXACT.value, due, "Africa/Lagos") is False
    assert is_past_due(due, DuePrecision.EXACT.value, due + timedelta(seconds=1), "Africa/Lagos") is True


def test_commitment_stays_pending_before_and_on_the_due_date(db_session: Session) -> None:
    business, commitment = _payment_commitment(db_session, "before-shop")

    before = run_evaluation(db_session, business.id, BEFORE_DUE)
    on_due_day = run_evaluation(db_session, business.id, DUE_AFTERNOON)

    assert before.commitments_missed == 0
    assert before.signals_created == 0
    assert on_due_day.signals_created == 0
    assert commitment.status == "PENDING"
    assert _count(db_session, Signal) == 0


def test_overdue_payment_opens_one_signal_and_replay_keeps_it(db_session: Session) -> None:
    business, commitment = _payment_commitment(db_session, "overdue-shop")

    first = run_evaluation(db_session, business.id, AFTER_DUE)
    second = run_evaluation(db_session, business.id, AFTER_DUE.replace(hour=18))
    signal = db_session.scalar(select(Signal))

    assert first.evaluators_run == 2
    assert first.commitments_missed == 1
    assert first.signals_created == 1
    assert first.signals_existing == 0
    assert second.commitments_missed == 0
    assert second.signals_created == 0
    assert second.signals_existing == 1
    assert commitment.status == "MISSED"
    assert signal is not None
    assert signal.signal_type == "OVERDUE_PAYMENT"
    assert signal.category == "REVENUE"
    assert signal.severity == "HIGH"
    assert signal.status == "OPEN"
    assert signal.commitment_id == commitment.id
    assert signal.event_id == commitment.source_event_id
    assert signal.customer_id == commitment.customer_id
    assert signal.financial_impact_amount == Decimal("150000.00")
    assert signal.currency == "NGN"
    assert "150000" in signal.description
    assert "not been fulfilled" in signal.description
    assert _count(db_session, Signal) == 1


def test_payment_claim_does_not_fulfill_the_commitment(db_session: Session) -> None:
    business, commitment = _payment_commitment(db_session, "claim-does-not-pay")
    conversation = db_session.get(Conversation, commitment.source_message_id and _conversation_id(db_session, commitment))
    assert conversation is not None
    claim = _message(
        db_session,
        business,
        conversation,
        "I sent the ₦150,000.",
        datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
    )
    analyzed = analyze_stored_message(db_session, claim.id, business.id, BEFORE_DUE)

    result = run_evaluation(db_session, business.id, AFTER_DUE)

    assert analyzed.events[0].event_type == "PAYMENT_CLAIM"
    assert analyzed.events[0].extracted_data["payment_verified"] is False
    assert result.commitments_missed == 1
    assert commitment.status == "MISSED"
    assert _count(db_session, Signal) == 1
    assert db_session.scalar(select(Signal.signal_type)) == "OVERDUE_PAYMENT"


def test_open_overdue_signal_is_unique_for_a_commitment(db_session: Session) -> None:
    business, commitment = _payment_commitment(db_session, "unique-shop")
    first = _signal_row(business, commitment)
    db_session.add(first)
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(_signal_row(business, commitment))
            db_session.flush()

    assert _count(db_session, Signal) == 1


def test_failed_signal_insert_does_not_leave_a_missed_commitment(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business, commitment = _payment_commitment(db_session, "atomic-shop")
    db_session.commit()

    def fail(session: Session, signal: Signal) -> None:
        raise RuntimeError("signal insert failed")

    monkeypatch.setattr("app.evaluators.overdue_payment.persist_new_signal", fail)

    with pytest.raises(RuntimeError, match="signal insert failed"):
        run_evaluation(db_session, business.id, AFTER_DUE)

    db_session.expire_all()
    stored = db_session.get(Commitment, commitment.id)
    assert stored is not None
    assert stored.status == "PENDING"
    assert _count(db_session, Signal) == 0


def test_unanswered_request_waits_for_the_threshold_then_opens_once(db_session: Session) -> None:
    business, event = _request_event(db_session, "request-shop", datetime(2026, 9, 24, 8, 0, tzinfo=LAGOS))

    early = run_evaluation(db_session, business.id, datetime(2026, 9, 24, 8, 59, tzinfo=LAGOS))
    assert early.signals_created == 0
    assert _count(db_session, Signal) == 0

    due = run_evaluation(db_session, business.id, datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS))
    again = run_evaluation(db_session, business.id, datetime(2026, 9, 24, 12, 0, tzinfo=LAGOS))
    signal = db_session.scalar(select(Signal))
    assert due.signals_created == 1
    assert due.commitments_missed == 0
    assert again.signals_created == 0
    assert again.signals_existing == 1
    assert signal is not None
    assert signal.signal_type == "UNANSWERED_REQUEST"
    assert signal.severity == "MEDIUM"
    assert signal.category == "OPERATIONS"
    assert signal.status == "OPEN"
    assert signal.event_id == event.id
    assert signal.commitment_id is None
    assert signal.financial_impact_amount is None
    assert _count(db_session, Signal) == 1


def test_business_reply_before_the_threshold_prevents_the_signal(db_session: Session) -> None:
    asked_at = datetime(2026, 9, 24, 8, 0, tzinfo=LAGOS)
    business, event = _request_event(db_session, "replied-shop", asked_at)
    conversation = db_session.get(Conversation, event.conversation_id)
    assert conversation is not None
    _message(
        db_session,
        business,
        conversation,
        "The wholesale price is NGN 4500 per unit.",
        asked_at + timedelta(minutes=20),
        sender_type="business",
        direction="outbound",
    )

    result = run_evaluation(db_session, business.id, asked_at + timedelta(hours=3))

    assert result.signals_created == 0
    assert _count(db_session, Signal) == 0


def test_evaluation_does_not_cross_businesses(db_session: Session) -> None:
    owner, _commitment = _payment_commitment(db_session, "owner-shop")
    other = Business(name="Other", slug="other-eval", default_currency="NGN", timezone="Africa/Lagos")
    db_session.add(other)
    db_session.flush()

    isolated = run_evaluation(db_session, other.id, AFTER_DUE)
    owner_commitment = db_session.scalar(select(Commitment).where(Commitment.business_id == owner.id))

    assert isolated.signals_created == 0
    assert isolated.commitments_missed == 0
    assert owner_commitment is not None
    assert owner_commitment.status == "PENDING"
    assert _count(db_session, Signal) == 0

    run_evaluation(db_session, owner.id, AFTER_DUE)
    assert _count(db_session, Signal) == 1
    assert db_session.scalar(select(Signal.business_id)) == owner.id


def test_same_state_and_reference_time_produce_the_same_result(db_session: Session) -> None:
    left_business, _left = _payment_commitment(db_session, "det-left")
    right_business, _right = _payment_commitment(db_session, "det-right")

    left = run_evaluation(db_session, left_business.id, AFTER_DUE)
    right = run_evaluation(db_session, right_business.id, AFTER_DUE)
    signals = list(db_session.scalars(select(Signal).order_by(Signal.business_id)))

    assert (left.commitments_missed, left.signals_created, left.signals_existing) == (1, 1, 0)
    assert (right.commitments_missed, right.signals_created, right.signals_existing) == (
        left.commitments_missed,
        left.signals_created,
        left.signals_existing,
    )
    assert len(signals) == 2
    assert signals[0].signal_type == signals[1].signal_type == "OVERDUE_PAYMENT"
    assert signals[0].severity == signals[1].severity == "HIGH"
    assert signals[0].financial_impact_amount == signals[1].financial_impact_amount
    assert signals[0].title == signals[1].title
    assert signals[0].description == signals[1].description


def test_unknown_business_is_rejected(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        run_evaluation(db_session, uuid.uuid4(), AFTER_DUE)
    assert _count(db_session, Signal) == 0


def test_seeded_adaeze_timeline(db_session: Session) -> None:
    assert seed_demo(db_session) == 4
    business = db_session.scalar(select(Business).where(Business.slug == "adaeze-wears"))
    assert business is not None
    messages = {
        message.content: message
        for message in db_session.scalars(select(Message).where(Message.business_id == business.id))
    }
    for content in (PAYMENT_CLAIM_TEXT, PAYMENT_PROMISE_TEXT, GREETING_TEXT, UNANSWERED_REQUEST_TEXT):
        analyze_stored_message(db_session, messages[content].id, business.id, BEFORE_DUE)

    before = run_evaluation(db_session, business.id, BEFORE_DUE)
    promise = db_session.scalar(
        select(Commitment).where(Commitment.business_id == business.id)
    )
    assert before.commitments_missed == 0
    assert before.signals_created == 0
    assert promise is not None
    assert promise.status == "PENDING"
    assert promise.due_at is not None
    assert promise.due_at.astimezone(LAGOS) == DUE_START

    after = run_evaluation(db_session, business.id, AFTER_DUE)
    replay = run_evaluation(db_session, business.id, AFTER_DUE.replace(hour=15))
    overdue = list(
        db_session.scalars(
            select(Signal).where(Signal.business_id == business.id, Signal.signal_type == "OVERDUE_PAYMENT")
        )
    )
    requests = list(
        db_session.scalars(
            select(Signal).where(Signal.business_id == business.id, Signal.signal_type == "UNANSWERED_REQUEST")
        )
    )

    assert after.commitments_missed == 1
    assert after.signals_created == 2
    assert promise.status == "MISSED"
    assert len(overdue) == 1
    assert overdue[0].financial_impact_amount == Decimal("150000.00")
    assert len(requests) == 1
    assert replay.signals_created == 0
    assert replay.signals_existing == 2
    assert _count(db_session, Signal) == 2


def test_evaluation_and_signal_endpoints(api_client: TestClient) -> None:
    business = api_client.post("/api/businesses", json={"name": "Signal Shop", "slug": "signal-shop"}).json()
    customer = api_client.post(
        f"/api/businesses/{business['id']}/customers",
        json={"name": "Amaka Bello", "contact_identifier": "2348012222222"},
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
            "content": PAYMENT_PROMISE_TEXT,
            "occurred_at": "2026-09-22T10:00:00Z",
        },
    ).json()
    analyzed = api_client.post(
        f"/api/messages/{message['id']}/analyze",
        json={"business_id": business["id"], "reference_time": "2026-09-24T09:00:00+01:00"},
    )
    before = api_client.post(
        "/api/evaluations/run",
        json={"business_id": business["id"], "reference_time": "2026-09-24T09:00:00+01:00"},
    )
    after = api_client.post(
        "/api/evaluations/run",
        json={"business_id": business["id"], "reference_time": "2026-09-26T09:00:00+01:00"},
    )
    replay = api_client.post(
        "/api/evaluations/run",
        json={"business_id": business["id"], "reference_time": "2026-09-26T18:00:00+01:00"},
    )
    listed = api_client.get("/api/signals", params={"business_id": business["id"], "signal_type": "OVERDUE_PAYMENT"})
    hidden = api_client.get("/api/signals", params={"business_id": business["id"], "severity": "LOW"})
    naive = api_client.post(
        "/api/evaluations/run",
        json={"business_id": business["id"], "reference_time": "2026-09-26T09:00:00"},
    )
    missing = api_client.post(
        "/api/evaluations/run",
        json={"business_id": str(uuid.uuid4()), "reference_time": "2026-09-26T09:00:00+01:00"},
    )

    assert analyzed.status_code == 200
    assert before.status_code == 200
    assert before.json()["signals_created"] == 0
    assert after.status_code == 200
    body = after.json()
    assert body["commitments_missed"] == 1
    assert body["signals_created"] == 1
    assert body["evaluators_run"] == 2
    assert replay.json()["signals_created"] == 0
    assert replay.json()["signals_existing"] == 1
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    signal = listed.json()[0]
    assert signal["severity"] == "HIGH"
    assert signal["status"] == "OPEN"
    assert Decimal(signal["financial_impact_amount"]) == Decimal("150000")
    fetched = api_client.get(f"/api/signals/{signal['id']}", params={"business_id": business["id"]})
    wrong_business = api_client.get(f"/api/signals/{signal['id']}", params={"business_id": str(uuid.uuid4())})
    assert fetched.status_code == 200
    assert fetched.json()["id"] == signal["id"]
    assert wrong_business.status_code == 404
    assert hidden.json() == []
    assert naive.status_code == 422
    assert missing.status_code == 404


def _payment_commitment(session: Session, slug: str) -> tuple[Business, Commitment]:
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
    message = _message(
        session,
        business,
        conversation,
        PAYMENT_PROMISE_TEXT,
        datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
    )
    event = BusinessEvent(
        business_id=business.id,
        event_type="PAYMENT_COMMITMENT",
        customer_id=customer.id,
        conversation_id=conversation.id,
        source_message_id=message.id,
        confidence=Decimal("0.880"),
        urgency="MEDIUM",
        extracted_data={"amount": "150000", "currency": "NGN"},
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
        due_at=DUE_START,
        due_text="Friday",
        due_precision="DATE",
        amount=Decimal("150000.00"),
        currency="NGN",
        status="PENDING",
    )
    session.add(commitment)
    session.flush()
    return business, commitment


def _request_event(session: Session, slug: str, occurred_at: datetime) -> tuple[Business, BusinessEvent]:
    business = Business(name=slug, slug=slug, default_currency="NGN", timezone="Africa/Lagos")
    session.add(business)
    session.flush()
    customer = Customer(
        business_id=business.id,
        name="Ngozi Eze",
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
    message = _message(session, business, conversation, UNANSWERED_REQUEST_TEXT, occurred_at)
    event = BusinessEvent(
        business_id=business.id,
        event_type="UNANSWERED_REQUEST",
        customer_id=customer.id,
        conversation_id=conversation.id,
        source_message_id=message.id,
        confidence=Decimal("0.850"),
        urgency="MEDIUM",
        extracted_data={"description": "Customer asked for the wholesale price and is waiting for a reply."},
        occurred_at=occurred_at,
    )
    session.add(event)
    session.flush()
    return business, event


def _message(
    session: Session,
    business: Business,
    conversation: Conversation,
    content: str,
    occurred_at: datetime,
    sender_type: str = "customer",
    direction: str = "inbound",
) -> Message:
    message = Message(
        business_id=business.id,
        conversation_id=conversation.id,
        sender_type=sender_type,
        direction=direction,
        content=content,
        occurred_at=occurred_at,
    )
    session.add(message)
    session.flush()
    return message


def _signal_row(business: Business, commitment: Commitment) -> Signal:
    return Signal(
        business_id=business.id,
        signal_type="OVERDUE_PAYMENT",
        category="REVENUE",
        severity="HIGH",
        title="Payment overdue",
        description="Revenue at risk: NGN 150000.",
        status="OPEN",
        confidence=Decimal("1.000"),
        financial_impact_amount=Decimal("150000.00"),
        currency="NGN",
        event_id=commitment.source_event_id,
        customer_id=commitment.customer_id,
        commitment_id=commitment.id,
    )


def _conversation_id(session: Session, commitment: Commitment) -> uuid.UUID:
    message = session.get(Message, commitment.source_message_id)
    assert message is not None
    return message.conversation_id


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)
