from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.heuristic import HeuristicAIProvider
from app.core.config import get_settings
from app.demo.clock import AFTER_DUE, BEFORE_DUE
from app.domain.errors import ConflictError
from app.main import app
from app.models import Action, Business, BusinessEvent, Commitment, Conversation, Customer, Message, Signal
from app.seed.demo import GREETING_TEXT
from app.services.actions import approve_action, recommend_actions, reject_action
from app.services.analysis import analyze_stored_message
from app.services.demo import reset_demo, run_demo
from app.services.evaluation import run_evaluation

MVP_PATHS = {
    "/api/health": {"get"},
    "/api/messages/{message_id}/analyze": {"post"},
    "/api/evaluations/run": {"post"},
    "/api/signals": {"get"},
    "/api/signals/{signal_id}": {"get"},
    "/api/actions": {"get"},
    "/api/actions/{action_id}": {"get"},
    "/api/actions/{action_id}/approve": {"post"},
    "/api/actions/{action_id}/reject": {"post"},
    "/api/dashboard/summary": {"get"},
    "/api/system/ai-provider": {"get"},
    "/api/system/demo": {"get"},
    "/api/demo/reset": {"post"},
    "/api/demo/run": {"post"},
    "/api/integrations/demo/messages": {"get", "post"},
}


def test_openapi_lists_the_mvp_contract() -> None:
    paths = app.openapi()["paths"]
    for path, methods in MVP_PATHS.items():
        assert path in paths
        assert methods <= set(paths[path])


def test_demo_routes_are_hidden_when_demo_mode_is_off(api_client: TestClient) -> None:
    _demo_mode(False)
    try:
        assert api_client.post("/api/demo/reset").status_code == 404
        assert api_client.post("/api/demo/run").status_code == 404
        status = api_client.get("/api/system/demo")
        assert status.status_code == 200
        assert status.json() == {"enabled": False}
    finally:
        get_settings.cache_clear()


def test_reset_restores_only_the_demo_business(db_session: Session) -> None:
    other = Business(name="Other Shop", slug="other-shop", default_currency="NGN", timezone="Africa/Lagos")
    db_session.add(other)
    db_session.flush()
    customer = Customer(business_id=other.id, name="Other", contact_identifier="2348099999999", status="ACTIVE")
    db_session.add(customer)
    db_session.flush()
    conversation = Conversation(
        business_id=other.id,
        customer_id=customer.id,
        channel="simulated",
        status="OPEN",
    )
    db_session.add(conversation)
    db_session.flush()
    message = Message(
        business_id=other.id,
        conversation_id=conversation.id,
        sender_type="customer",
        direction="inbound",
        content="Leave this alone.",
        occurred_at=BEFORE_DUE,
    )
    db_session.add(message)
    db_session.flush()

    state = reset_demo(db_session)

    assert state.business == "Adaeze Wears"
    assert state.messages == 4
    assert state.events == 0
    assert state.commitments == 0
    assert state.signals == 0
    assert state.actions == 0
    assert db_session.get(Message, message.id) is not None
    assert db_session.scalar(select(func.count()).select_from(Message).where(Message.business_id == other.id)) == 1


def test_demo_story_reaches_an_approved_follow_up(db_session: Session) -> None:
    first = run_demo(db_session, HeuristicAIProvider())
    second = run_demo(db_session, HeuristicAIProvider())

    assert first.business == "Adaeze Wears"
    assert first.provider == "heuristic"
    assert first.messages_analyzed == 4
    assert first.events_created == 3
    assert first.commitments_created == 1
    assert first.commitments_missed == 1
    assert first.signals_created == 3
    assert first.actions_created == 3
    assert first.evaluated_before == BEFORE_DUE
    assert first.evaluated_after == AFTER_DUE
    assert second.events_created == 3
    assert second.actions_created == 3
    assert _count(db_session, BusinessEvent) == 3
    assert _count(db_session, Commitment) == 1

    business = db_session.scalar(select(Business).where(Business.slug == "adaeze-wears"))
    assert business is not None
    claim = _event(db_session, business.id, "PAYMENT_CLAIM")
    promise = _event(db_session, business.id, "PAYMENT_COMMITMENT")
    request = _event(db_session, business.id, "UNANSWERED_REQUEST")
    commitment = db_session.scalar(select(Commitment).where(Commitment.business_id == business.id))
    signals = {
        row.signal_type: row
        for row in db_session.scalars(select(Signal).where(Signal.business_id == business.id))
    }
    greeting = db_session.scalar(select(Message).where(Message.content == GREETING_TEXT))

    assert claim is not None and claim.extracted_data["payment_verified"] is False
    assert promise is not None
    assert request is not None
    assert commitment is not None
    assert commitment.status == "MISSED"
    assert commitment.amount == Decimal("150000.00")
    assert commitment.currency == "NGN"
    assert commitment.due_text == "Friday"
    assert signals["OVERDUE_PAYMENT"].status == "OPEN"
    assert signals["OVERDUE_PAYMENT"].severity == "HIGH"
    assert signals["UNANSWERED_REQUEST"].status == "OPEN"
    assert signals["PAYMENT_CLAIM"].status == "OPEN"
    assert "not verified" in signals["PAYMENT_CLAIM"].description
    assert greeting is not None
    greeting_customer = db_session.get(Conversation, greeting.conversation_id)
    assert greeting_customer is not None
    assert _events_for_message(db_session, greeting.id) == 0
    assert _rows_for(db_session, Commitment, Commitment.source_message_id, greeting.id) == 0
    assert _rows_for(db_session, Signal, Signal.customer_id, greeting_customer.customer_id) == 0
    assert _count_direction(db_session, "outbound") == 0

    follow_up = _action(db_session, business.id, "FOLLOW_UP_CUSTOMER")
    reply = _action(db_session, business.id, "RESPOND_TO_REQUEST")
    assert follow_up.status == "PROPOSED"
    assert reply.status == "PROPOSED"
    assert "received" not in (follow_up.proposed_content or "").lower()

    approved = approve_action(db_session, follow_up.id, business.id)
    assert approved.status == "APPROVED"
    assert approved.approved_at is not None
    assert approved.executed_at is None
    with pytest.raises(ConflictError):
        approve_action(db_session, follow_up.id, business.id)
    with pytest.raises(ConflictError):
        reject_action(db_session, follow_up.id, business.id)


def test_reprocessing_the_same_demo_does_not_duplicate_rows(db_session: Session) -> None:
    run_demo(db_session, HeuristicAIProvider())
    business = db_session.scalar(select(Business).where(Business.slug == "adaeze-wears"))
    assert business is not None
    messages = list(db_session.scalars(select(Message).where(Message.business_id == business.id)).all())

    for message in messages:
        analyze_stored_message(db_session, message.id, business.id, BEFORE_DUE, HeuristicAIProvider())
    run_evaluation(db_session, business.id, BEFORE_DUE)
    again = run_evaluation(db_session, business.id, AFTER_DUE)
    recommended = recommend_actions(db_session, business.id)

    assert again.signals_created == 0
    assert again.signals_existing == 3
    assert recommended.actions_created == 0
    assert recommended.actions_existing == 3
    assert _rows_for(db_session, BusinessEvent, BusinessEvent.business_id, business.id) == 3
    assert _rows_for(db_session, Commitment, Commitment.business_id, business.id) == 1
    assert _rows_for(db_session, Signal, Signal.business_id, business.id) == 3
    assert _rows_for(db_session, Action, Action.business_id, business.id) == 3


def test_demo_run_endpoint_returns_the_measured_story(api_client: TestClient) -> None:
    _demo_mode(True)
    try:
        response = api_client.post("/api/demo/run")
    finally:
        _demo_mode(False)

    assert response.status_code == 200
    body = response.json()
    assert body["business"] == "Adaeze Wears"
    assert body["provider"] == "heuristic"
    assert body["messages_analyzed"] == 4
    assert body["events_created"] == 3
    assert body["commitments_created"] == 1
    assert body["commitments_missed"] == 1
    assert body["signals_created"] == 3
    assert body["actions_created"] == 3
    assert body["evaluated_before"].startswith("2026-09-24T09:00:00")
    assert body["evaluated_after"].startswith("2026-09-26T09:00:00")
    assert "api_key" not in response.text.lower()


def _demo_mode(enabled: bool) -> None:
    import os

    os.environ["VIGIE_DEMO_MODE"] = "true" if enabled else "false"
    get_settings.cache_clear()


def _event(session: Session, business_id, event_type: str) -> BusinessEvent | None:
    return session.scalar(
        select(BusinessEvent).where(
            BusinessEvent.business_id == business_id,
            BusinessEvent.event_type == event_type,
        )
    )


def _rows_for(session: Session, model: type, column, value) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(column == value)) or 0)


def _events_for_message(session: Session, message_id) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(BusinessEvent).where(BusinessEvent.source_message_id == message_id)
        )
        or 0
    )


def _action(session: Session, business_id, action_type: str) -> Action:
    action = session.scalar(
        select(Action).where(Action.business_id == business_id, Action.action_type == action_type)
    )
    assert action is not None
    return action


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _count_direction(session: Session, direction: str) -> int:
    return int(
        session.scalar(select(func.count()).select_from(Message).where(Message.direction == direction)) or 0
    )
