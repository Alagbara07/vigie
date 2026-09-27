import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demo.clock import AFTER_DUE
from app.domain.enums import MessageSource
from app.integrations.messages import NormalizedMessage
from app.models import Action, Business, BusinessEvent, Commitment, Message, Signal
from app.services.actions import approve_action, recommend_actions
from app.services.evaluation import run_evaluation

LAGOS = ZoneInfo("Africa/Lagos")
WHEN = datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS)
PROMISE = "I'll pay the remaining ₦150,000 on Friday."


def test_normalized_message_rejects_unknown_source_and_blank_fields() -> None:
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(
            {
                "business_id": str(uuid.uuid4()),
                "source": "sms",
                "external_message_id": "WA123",
                "external_conversation_id": "thread-1",
                "customer_name": "Amaka Bello",
                "text": PROMISE,
                "timestamp": WHEN.isoformat(),
            }
        )
    with pytest.raises(ValidationError):
        NormalizedMessage(
            business_id=uuid.uuid4(),
            source=MessageSource.DEMO,
            external_message_id="   ",
            external_conversation_id="thread-1",
            customer_name="Amaka Bello",
            text=PROMISE,
            timestamp=WHEN,
        )
    with pytest.raises(ValidationError):
        NormalizedMessage(
            business_id=uuid.uuid4(),
            source=MessageSource.WHATSAPP,
            external_message_id="WA123",
            external_conversation_id="thread-1",
            customer_name="Amaka Bello",
            text="  ",
            timestamp=WHEN,
        )


def test_demo_connector_is_hidden_when_demo_mode_is_off(api_client: TestClient) -> None:
    _demo_mode(False)
    business_id = str(uuid.uuid4())
    assert api_client.post("/api/integrations/demo/messages", json=_payload(business_id)).status_code == 404
    assert api_client.get("/api/integrations/demo/messages", params={"business_id": business_id}).status_code == 404


def test_demo_message_becomes_a_commitment_without_duplicates(api_client: TestClient, db_session: Session) -> None:
    _demo_mode(True)
    business = _business(db_session, "adaeze-wears")
    other = _business(db_session, "other-shop")
    payload = _payload(str(business.id))

    try:
        first = api_client.post("/api/integrations/demo/messages", json=payload)
        second = api_client.post("/api/integrations/demo/messages", json=payload)
        missing = api_client.post("/api/integrations/demo/messages", json=_payload(str(uuid.uuid4())))
        listed = api_client.get("/api/integrations/demo/messages", params={"business_id": str(business.id)})
        isolated = api_client.get("/api/integrations/demo/messages", params={"business_id": str(other.id)})
        blank = api_client.post(
            "/api/integrations/demo/messages",
            json={**payload, "text": "  ", "external_message_id": ""},
        )
    finally:
        _demo_mode(False)

    assert first.status_code == 200
    body = first.json()
    assert body["created"] is True
    assert body["analyzed"] is True
    assert body["source"] == "demo"
    assert body["source_label"] == "WhatsApp Business"
    assert body["connection"] == "Demo connection"
    assert body["events"] == ["PAYMENT_COMMITMENT"]
    assert "api_key" not in first.text.lower()
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["message_id"] == body["message_id"]
    assert second.json()["analyzed"] is False
    assert missing.status_code == 404
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert isolated.status_code == 200
    assert isolated.json() == []
    assert _count(db_session, Message) == 1
    assert _count(db_session, BusinessEvent) == 1
    commitment = db_session.scalar(select(Commitment))
    assert commitment is not None
    assert commitment.status == "PENDING"
    assert commitment.amount == Decimal("150000.00")
    assert _count(db_session, Signal) == 0
    assert blank.status_code == 422


def test_demo_pipeline_reaches_an_approved_follow_up_without_sending(api_client: TestClient, db_session: Session) -> None:
    _demo_mode(True)
    business = _business(db_session, "pipeline-shop")
    try:
        created = api_client.post("/api/integrations/demo/messages", json=_payload(str(business.id), "pipe-1"))
    finally:
        _demo_mode(False)
    assert created.status_code == 200

    evaluated = run_evaluation(db_session, business.id, AFTER_DUE)
    assert evaluated.commitments_missed == 1
    assert evaluated.signals_created == 1
    signal = db_session.scalar(select(Signal).where(Signal.business_id == business.id))
    assert signal is not None
    assert signal.signal_type == "OVERDUE_PAYMENT"
    detail = api_client.get(f"/api/signals/{signal.id}", params={"business_id": str(business.id)})
    assert detail.status_code == 200
    evidence = detail.json()["evidence"]
    assert evidence["source"] == "demo"
    assert evidence["source_label"] == "WhatsApp Business"
    assert evidence["connection"] == "Demo connection"
    assert evidence["content"] == PROMISE
    assert evidence["external_message_id"] == "pipe-1"

    recommended = recommend_actions(db_session, business.id)
    assert recommended.actions_created == 1
    follow_up = db_session.scalar(select(Action).where(Action.business_id == business.id))
    assert follow_up is not None
    assert follow_up.action_type == "FOLLOW_UP_CUSTOMER"
    approved = approve_action(db_session, follow_up.id, business.id)
    assert approved.status == "APPROVED"
    assert approved.executed_at is None
    outbound = db_session.scalar(select(func.count()).select_from(Message).where(Message.direction == "outbound"))
    assert outbound == 0
    wrong = api_client.get(f"/api/signals/{signal.id}", params={"business_id": str(uuid.uuid4())})
    assert wrong.status_code == 404


def _payload(business_id: str, external_id: str = "demo-wa-001") -> dict[str, str]:
    return {
        "business_id": business_id,
        "customer_name": "Amaka Bello",
        "conversation_id": "demo-amaka-001",
        "external_message_id": external_id,
        "text": PROMISE,
        "timestamp": WHEN.isoformat(),
    }


def _business(session: Session, slug: str) -> Business:
    business = Business(name=slug, slug=slug, default_currency="NGN", timezone="Africa/Lagos")
    session.add(business)
    session.commit()
    return business


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _demo_mode(enabled: bool) -> None:
    import os

    from app.core.config import get_settings

    os.environ["VIGIE_DEMO_MODE"] = "true" if enabled else "false"
    get_settings.cache_clear()
