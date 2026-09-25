import socket
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.actions.rules import draft_for_signal
from app.models import Action
from app.seed.demo import PAYMENT_PROMISE_TEXT, UNANSWERED_REQUEST_TEXT

AFTER_DUE = "2026-09-26T09:00:00+01:00"
AFTER_REQUEST = "2026-09-24T10:00:00+01:00"


def test_rules_follow_the_signal_and_do_not_invent_a_reply() -> None:
    overdue = draft_for_signal(
        "OVERDUE_PAYMENT",
        customer_name="Amaka Bello",
        amount=Decimal("150000"),
        currency="NGN",
    )
    request = draft_for_signal("UNANSWERED_REQUEST", customer_name="Ngozi Eze", amount=None, currency=None)
    untouched = draft_for_signal("NEW_LEAD", customer_name="Tunde Adeyemi", amount=None, currency=None)

    assert overdue is not None
    assert overdue.action_type == "FOLLOW_UP_CUSTOMER"
    assert "Amaka" in overdue.proposed_content
    assert "₦150,000" in overdue.proposed_content
    assert "received" not in overdue.proposed_content.lower()
    assert "past its due date" in overdue.description
    assert request is not None
    assert request.action_type == "RESPOND_TO_REQUEST"
    assert "reply yourself" in request.proposed_content
    assert "₦" not in request.proposed_content
    assert "100" not in request.proposed_content
    assert untouched is None


def test_overdue_payment_creates_one_follow_up(api_client: TestClient) -> None:
    business_id, signal_id = _open_signal(api_client, "follow-up-shop", "Amaka Bello", PAYMENT_PROMISE_TEXT, AFTER_DUE)
    before = api_client.get(f"/api/signals/{signal_id}", params={"business_id": business_id})
    created = api_client.post("/api/actions/recommend", json={"business_id": business_id, "signal_id": signal_id})
    repeated = [
        api_client.post("/api/actions/recommend", json={"business_id": business_id, "signal_id": signal_id})
        for _ in range(4)
    ]
    listed = api_client.get("/api/actions", params={"business_id": business_id, "signal_id": signal_id})
    detail = api_client.get(f"/api/signals/{signal_id}", params={"business_id": business_id})
    feed = api_client.get("/api/signals", params={"business_id": business_id})

    assert before.status_code == 200
    assert before.json()["action"] is None
    assert created.status_code == 200
    body = created.json()
    assert body["actions_created"] == 1
    assert body["actions_existing"] == 0
    action = body["actions"][0]
    assert action["action_type"] == "FOLLOW_UP_CUSTOMER"
    assert action["status"] == "PROPOSED"
    assert action["business_id"] == business_id
    assert action["signal_id"] == signal_id
    assert action["executed_at"] is None
    assert "₦150,000" in action["proposed_content"]
    assert "received" not in action["proposed_content"].lower()
    assert "past its due date" in action["description"]
    assert all(item.json()["actions_created"] == 0 for item in repeated)
    assert all(item.json()["actions_existing"] == 1 for item in repeated)
    assert len(listed.json()) == 1
    assert detail.json()["action"]["id"] == action["id"]
    assert feed.json()[0]["action"]["action_type"] == "FOLLOW_UP_CUSTOMER"


def test_unanswered_request_asks_the_owner_to_reply(api_client: TestClient) -> None:
    business_id, signal_id = _open_signal(
        api_client,
        "reply-shop",
        "Ngozi Eze",
        UNANSWERED_REQUEST_TEXT,
        AFTER_REQUEST,
        occurred_at="2026-09-24T07:30:00Z",
    )
    created = api_client.post("/api/actions/recommend", json={"business_id": business_id})
    action = created.json()["actions"][0]

    assert created.status_code == 200
    assert created.json()["actions_created"] == 1
    assert action["action_type"] == "RESPOND_TO_REQUEST"
    assert action["signal_id"] == signal_id
    assert "reply yourself" in action["proposed_content"]
    assert "has not replied" in action["description"]
    assert "₦" not in action["proposed_content"]
    assert "100" not in action["proposed_content"]


def test_database_rejects_a_duplicate_action(api_client: TestClient, db_session: Session) -> None:
    business_id, signal_id = _open_signal(api_client, "unique-shop", "Amaka Bello", PAYMENT_PROMISE_TEXT, AFTER_DUE)
    api_client.post("/api/actions/recommend", json={"business_id": business_id, "signal_id": signal_id})
    duplicate = Action(
        business_id=uuid.UUID(business_id),
        signal_id=uuid.UUID(signal_id),
        action_type="FOLLOW_UP_CUSTOMER",
        status="PROPOSED",
        title="Follow up with customer",
        description="Recommended because this payment commitment is past its due date and remains unfulfilled.",
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()


def test_approval_records_the_decision_and_sends_nothing(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    business_id, signal_id = _open_signal(api_client, "approve-shop", "Amaka Bello", PAYMENT_PROMISE_TEXT, AFTER_DUE)
    action_id = api_client.post(
        "/api/actions/recommend",
        json={"business_id": business_id, "signal_id": signal_id},
    ).json()["actions"][0]["id"]

    def refuse_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("approval opened a network connection")

    monkeypatch.setattr(socket, "create_connection", refuse_network)
    approved = api_client.post(f"/api/actions/{action_id}/approve", json={"business_id": business_id})
    again = api_client.post(f"/api/actions/{action_id}/approve", json={"business_id": business_id})
    rejected = api_client.post(f"/api/actions/{action_id}/reject", json={"business_id": business_id})

    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "APPROVED"
    assert body["executed_at"] is None
    assert body["rejected_at"] is None
    approved_at = datetime.fromisoformat(body["approved_at"])
    assert approved_at.tzinfo is not None
    assert again.status_code == 409
    assert rejected.status_code == 409


def test_rejection_records_the_decision(api_client: TestClient) -> None:
    business_id, signal_id = _open_signal(api_client, "reject-shop", "Amaka Bello", PAYMENT_PROMISE_TEXT, AFTER_DUE)
    action_id = api_client.post(
        "/api/actions/recommend",
        json={"business_id": business_id, "signal_id": signal_id},
    ).json()["actions"][0]["id"]

    rejected = api_client.post(f"/api/actions/{action_id}/reject", json={"business_id": business_id})
    again = api_client.post(f"/api/actions/{action_id}/reject", json={"business_id": business_id})
    approved = api_client.post(f"/api/actions/{action_id}/approve", json={"business_id": business_id})

    assert rejected.status_code == 200
    body = rejected.json()
    assert body["status"] == "REJECTED"
    assert body["approved_at"] is None
    assert body["executed_at"] is None
    rejected_at = datetime.fromisoformat(body["rejected_at"])
    assert rejected_at.tzinfo is not None
    assert again.status_code == 409
    assert approved.status_code == 409


def test_another_business_cannot_read_or_decide_an_action(api_client: TestClient) -> None:
    business_id, signal_id = _open_signal(api_client, "owner-shop", "Amaka Bello", PAYMENT_PROMISE_TEXT, AFTER_DUE)
    other = api_client.post("/api/businesses", json={"name": "Other Shop", "slug": "other-action-shop"}).json()
    action_id = api_client.post(
        "/api/actions/recommend",
        json={"business_id": business_id, "signal_id": signal_id},
    ).json()["actions"][0]["id"]

    fetched = api_client.get(f"/api/actions/{action_id}", params={"business_id": other["id"]})
    listed = api_client.get("/api/actions", params={"business_id": other["id"]})
    approved = api_client.post(f"/api/actions/{action_id}/approve", json={"business_id": other["id"]})
    rejected = api_client.post(f"/api/actions/{action_id}/reject", json={"business_id": other["id"]})
    still = api_client.get(f"/api/actions/{action_id}", params={"business_id": business_id})

    assert fetched.status_code == 404
    assert listed.status_code == 200
    assert listed.json() == []
    assert approved.status_code == 404
    assert rejected.status_code == 404
    assert still.json()["status"] == "PROPOSED"


def _open_signal(
    api_client: TestClient,
    slug: str,
    customer_name: str,
    content: str,
    reference_time: str,
    occurred_at: str = "2026-09-22T10:00:00Z",
) -> tuple[str, str]:
    business = api_client.post("/api/businesses", json={"name": slug, "slug": slug}).json()
    customer = api_client.post(
        f"/api/businesses/{business['id']}/customers",
        json={"name": customer_name, "contact_identifier": f"23480{slug[:6]}"},
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
            "content": content,
            "occurred_at": occurred_at,
        },
    ).json()
    analyzed = api_client.post(
        f"/api/messages/{message['id']}/analyze",
        json={"business_id": business["id"], "reference_time": "2026-09-24T09:00:00+01:00"},
    )
    evaluated = api_client.post(
        "/api/evaluations/run",
        json={"business_id": business["id"], "reference_time": reference_time},
    )
    listed = api_client.get("/api/signals", params={"business_id": business["id"], "status": "OPEN"})
    assert analyzed.status_code == 200
    assert evaluated.status_code == 200
    assert evaluated.json()["signals_created"] == 1
    assert len(listed.json()) == 1
    return business["id"], listed.json()[0]["id"]
