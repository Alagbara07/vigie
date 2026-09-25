import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.factory import build_ai_provider, provider_status
from app.ai.nvidia import NvidiaAIProvider
from app.ai.prompt import SYSTEM_PROMPT
from app.ai.request import AnalysisRequest
from app.core.config import Settings
from app.domain.errors import AIProviderError, InvalidProposalError
from app.models import Business, BusinessEvent, Commitment, Conversation, Customer, Message, Signal
from app.seed.demo import PAYMENT_PROMISE_TEXT
from app.services.analysis import analyze_stored_message

LAGOS = ZoneInfo("Africa/Lagos")
REFERENCE_TIME = datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS)
FRIDAY = datetime(2026, 9, 25, tzinfo=LAGOS).date()


def test_prompt_keeps_claims_commitments_and_greetings_distinct() -> None:
    assert "I sent 150000" in SYSTEM_PROMPT
    assert "not a verified payment" in SYSTEM_PROMPT
    assert "I'll pay 150000 on Friday" in SYSTEM_PROMPT
    assert "not a fulfilled payment" in SYSTEM_PROMPT
    assert "UNANSWERED_REQUEST" in SYSTEM_PROMPT
    assert "no_business_event" in SYSTEM_PROMPT
    assert "due_at is always null" in SYSTEM_PROMPT


def test_provider_selection_stays_explicit() -> None:
    heuristic = build_ai_provider(Settings(ai_provider="heuristic", nvidia_api_key="unused-secret"))
    nvidia = build_ai_provider(
        Settings(
            ai_provider="nvidia",
            nvidia_api_key="test-key",
            nvidia_model="test-model",
            nvidia_base_url="https://example.test/v1",
            nvidia_timeout_seconds=5,
        )
    )

    assert heuristic.name == "heuristic"
    assert nvidia.name == "nvidia"
    assert isinstance(nvidia, NvidiaAIProvider)


def test_missing_nvidia_configuration_is_rejected_without_the_secret() -> None:
    settings = Settings(
        ai_provider="nvidia",
        nvidia_api_key="secret-key-value",
        nvidia_model="",
        nvidia_base_url="",
    )

    with pytest.raises(AIProviderError) as caught:
        build_ai_provider(settings)

    message = str(caught.value)
    assert "NVIDIA_MODEL" in message
    assert "NVIDIA_BASE_URL" in message
    assert "secret-key-value" not in message
    status = provider_status(settings)
    assert status.provider == "nvidia"
    assert status.configured is False


def test_provider_status_reports_the_selected_provider_without_secrets(api_client: TestClient) -> None:
    response = api_client.get("/api/system/ai-provider")

    assert response.status_code == 200
    assert set(response.json()) == {"provider", "configured", "model"}
    assert response.json()["provider"] == "heuristic"
    assert response.json()["configured"] is True
    assert response.json()["model"] is None


def test_unknown_provider_does_not_fall_back() -> None:
    with pytest.raises(AIProviderError):
        build_ai_provider(Settings(ai_provider="other"))
    status = provider_status(Settings(ai_provider="other"))
    assert status.configured is False


def test_nvidia_proposal_flows_through_validation_into_a_pending_commitment(db_session: Session) -> None:
    business, message = _thread(db_session, "nvidia-shop", PAYMENT_PROMISE_TEXT)
    provider = _provider(_ok(commitment_proposal(due_at="2030-01-01T00:00:00+00:00")))
    request = AnalysisRequest(
        content=PAYMENT_PROMISE_TEXT,
        occurred_at=message.occurred_at,
        reference_time=REFERENCE_TIME,
        timezone_name="Africa/Lagos",
        default_currency="NGN",
    )

    provider.analyze_message(request)

    assert _count(db_session, BusinessEvent) == 0
    assert _count(db_session, Commitment) == 0
    result = analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME, provider)

    assert result.provider == "nvidia"
    assert result.proposal.intent == "payment_commitment"
    assert len(result.events) == 1
    assert result.events[0].event_type == "PAYMENT_COMMITMENT"
    commitment = result.commitments[0]
    assert commitment.status == "PENDING"
    assert commitment.amount == Decimal("150000.00")
    assert commitment.due_text == "Friday"
    assert commitment.due_precision == "DATE"
    assert commitment.due_at is not None
    assert commitment.due_at.astimezone(LAGOS).date() == FRIDAY
    assert _count(db_session, Signal) == 0
    assert provider.last_latency_ms is not None


def test_malformed_nvidia_json_creates_nothing(db_session: Session) -> None:
    business, message = _thread(db_session, "nvidia-bad-json", PAYMENT_PROMISE_TEXT)
    provider = _provider(_ok("not json"))

    with pytest.raises(InvalidProposalError):
        analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME, provider)

    assert _count(db_session, BusinessEvent) == 0
    assert _count(db_session, Commitment) == 0


def test_invalid_nvidia_proposal_creates_nothing(db_session: Session) -> None:
    business, message = _thread(db_session, "nvidia-bad-shape", PAYMENT_PROMISE_TEXT)
    provider = _provider(_ok({"intent": "payment_commitment"}))

    with pytest.raises(InvalidProposalError):
        analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME, provider)

    assert _count(db_session, BusinessEvent) == 0


def test_nvidia_http_error_is_controlled(db_session: Session) -> None:
    business, message = _thread(db_session, "nvidia-http", PAYMENT_PROMISE_TEXT)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    provider = _provider(handler)

    with pytest.raises(AIProviderError, match="rejected"):
        analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME, provider)

    assert calls["count"] == 1
    assert _count(db_session, BusinessEvent) == 0


def test_nvidia_retries_one_server_error_then_accepts_the_proposal(db_session: Session) -> None:
    business, message = _thread(db_session, "nvidia-retry", PAYMENT_PROMISE_TEXT)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"error": "unavailable"})
        return _ok(commitment_proposal())(request)

    result = analyze_stored_message(
        db_session,
        message.id,
        business.id,
        REFERENCE_TIME,
        _provider(handler),
    )

    assert calls["count"] == 2
    assert result.commitments[0].status == "PENDING"


def test_nvidia_server_error_stops_after_one_retry(db_session: Session) -> None:
    business, message = _thread(db_session, "nvidia-down", PAYMENT_PROMISE_TEXT)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(502, json={"error": "down"})

    with pytest.raises(AIProviderError, match="could not complete"):
        analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME, _provider(handler))

    assert calls["count"] == 2
    assert _count(db_session, BusinessEvent) == 0


def test_nvidia_timeout_is_controlled(db_session: Session) -> None:
    business, message = _thread(db_session, "nvidia-timeout", PAYMENT_PROMISE_TEXT)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(AIProviderError, match="timed out"):
        analyze_stored_message(db_session, message.id, business.id, REFERENCE_TIME, _provider(handler))

    assert _count(db_session, BusinessEvent) == 0


def test_nvidia_logs_do_not_include_the_api_key(caplog: pytest.LogCaptureFixture) -> None:
    secret = "secret-key-value"
    provider = NvidiaAIProvider(
        api_key=secret,
        model="test-model",
        base_url="https://example.test/v1",
        timeout_seconds=5,
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "unauthorized"})),
    )
    request = AnalysisRequest(
        content="I'll pay the remaining ₦150,000 on Friday.",
        occurred_at=REFERENCE_TIME,
        reference_time=REFERENCE_TIME,
        timezone_name="Africa/Lagos",
        default_currency="NGN",
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AIProviderError):
            provider.analyze_message(request)

    assert secret not in caplog.text
    assert "Authorization" not in caplog.text


def commitment_proposal(due_at: str | None = None) -> dict[str, object]:
    return {
        "provider": "nvidia",
        "intent": "payment_commitment",
        "confidence": 0.88,
        "entities": [{"amount": "150000", "currency": "NGN"}],
        "proposed_events": [
            {
                "event_type": "PAYMENT_COMMITMENT",
                "confidence": 0.88,
                "urgency": "MEDIUM",
                "amount": "150000",
                "currency": "NGN",
                "due_at": due_at,
                "due_text": "Friday",
                "due_precision": None,
                "description": "Customer promised to pay NGN 150000 on Friday.",
            }
        ],
        "reasoning": "The customer promised a future payment.",
    }


def _ok(payload: dict[str, object] | str):
    content = payload if isinstance(payload, str) else json.dumps(payload)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content.decode())
        assert body["model"] == "test-model"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return handler


def _provider(handler) -> NvidiaAIProvider:
    return NvidiaAIProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.test/v1",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


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
