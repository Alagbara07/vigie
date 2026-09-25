import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.ai.dates import WEEKDAYS, resolve_weekday
from app.ai.request import AnalysisRequest
from app.domain.enums import DuePrecision, EventType, Urgency

PROVIDER_NAME = "heuristic"

CLAIM_CONFIDENCE = Decimal("0.910")
COMMITMENT_CONFIDENCE = Decimal("0.880")
REQUEST_CONFIDENCE = Decimal("0.850")
NO_EVENT_CONFIDENCE = Decimal("0.960")
CLAIM_URGENCY = Urgency.HIGH
COMMITMENT_URGENCY = Urgency.MEDIUM
REQUEST_URGENCY = Urgency.MEDIUM

_AMOUNT = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)(?:\s*)(k|m)?\b")
_THOUSAND = Decimal("1000")
_MILLION = Decimal("1000000")


class HeuristicAIProvider:
    """Deterministic development provider. This is not an NVIDIA integration."""

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def analyze_message(self, request: AnalysisRequest) -> dict[str, Any]:
        normalized = _normalize(request.content)
        if _is_payment_commitment(normalized):
            return _commitment_proposal(request, normalized)
        if _is_payment_claim(normalized):
            return _claim_proposal(request, normalized)
        if _is_unanswered_request(normalized):
            return _request_proposal()
        return _no_event_proposal()


def _normalize(content: str) -> str:
    text = content.lower().replace("’", "'").replace("₦", " ngn ")
    text = text.replace(",", "")
    return " ".join(text.split())


def _is_payment_commitment(text: str) -> bool:
    promises_payment = "i'll pay" in text or "i will pay" in text
    return promises_payment and "sent" not in text


def _is_payment_claim(text: str) -> bool:
    markers = ("i sent", "i have sent", "i transferred", "i have paid", "i paid")
    return any(marker in text for marker in markers)


def _is_unanswered_request(text: str) -> bool:
    return "how much" in text or "wholesale price" in text


def _claim_proposal(request: AnalysisRequest, text: str) -> dict[str, Any]:
    amount, currency = _money(text, request.default_currency)
    return _proposal(
        intent="payment_claim",
        confidence=CLAIM_CONFIDENCE,
        amount=amount,
        currency=currency,
        reasoning="The customer states that money was already sent. That is a claim, not a verified payment.",
        event=_event(
            event_type=EventType.PAYMENT_CLAIM,
            confidence=CLAIM_CONFIDENCE,
            urgency=CLAIM_URGENCY,
            amount=amount,
            currency=currency,
            description=_claim_description(amount, currency),
        ),
    )


def _commitment_proposal(request: AnalysisRequest, text: str) -> dict[str, Any]:
    amount, currency = _money(text, request.default_currency)
    weekday = _mentioned_weekday(text)
    due_at: datetime | None = None
    due_text: str | None = None
    due_precision: DuePrecision | None = None
    if weekday is not None:
        due_at = resolve_weekday(request.reference_time, weekday, request.timezone_name)
        due_text = weekday.capitalize()
        due_precision = DuePrecision.DATE
    return _proposal(
        intent="payment_commitment",
        confidence=COMMITMENT_CONFIDENCE,
        amount=amount,
        currency=currency,
        reasoning="The customer promised a future payment. The promise stays pending until a later check.",
        event=_event(
            event_type=EventType.PAYMENT_COMMITMENT,
            confidence=COMMITMENT_CONFIDENCE,
            urgency=COMMITMENT_URGENCY,
            amount=amount,
            currency=currency,
            description=_commitment_description(amount, currency, due_text),
            due_at=due_at,
            due_text=due_text,
            due_precision=due_precision,
        ),
    )


def _request_proposal() -> dict[str, Any]:
    return _proposal(
        intent="unanswered_request",
        confidence=REQUEST_CONFIDENCE,
        amount=None,
        currency=None,
        reasoning="The customer asked for information. A reply has not been established by this message.",
        event=_event(
            event_type=EventType.UNANSWERED_REQUEST,
            confidence=REQUEST_CONFIDENCE,
            urgency=REQUEST_URGENCY,
            amount=None,
            currency=None,
            description="Customer asked for the wholesale price and is waiting for a reply.",
        ),
    )


def _no_event_proposal() -> dict[str, Any]:
    return {
        "intent": "no_business_event",
        "confidence": str(NO_EVENT_CONFIDENCE),
        "entities": [],
        "proposed_events": [],
        "reasoning": "The message is ordinary conversation and does not describe a business event.",
        "provider": PROVIDER_NAME,
    }


def _proposal(
    *,
    intent: str,
    confidence: Decimal,
    amount: Decimal | None,
    currency: str | None,
    reasoning: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    entities: list[dict[str, str]] = []
    if amount is not None and currency is not None:
        entities.append({"amount": format(amount, "f"), "currency": currency})
    return {
        "intent": intent,
        "confidence": str(confidence),
        "entities": entities,
        "proposed_events": [event],
        "reasoning": reasoning,
        "provider": PROVIDER_NAME,
    }


def _event(
    *,
    event_type: EventType,
    confidence: Decimal,
    urgency: Urgency,
    amount: Decimal | None,
    currency: str | None,
    description: str,
    due_at: datetime | None = None,
    due_text: str | None = None,
    due_precision: DuePrecision | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type.value,
        "confidence": str(confidence),
        "urgency": urgency.value,
        "amount": None if amount is None else format(amount, "f"),
        "currency": currency,
        "due_at": None if due_at is None else due_at.isoformat(),
        "due_text": due_text,
        "due_precision": None if due_precision is None else due_precision.value,
        "description": description,
    }


def _money(text: str, default_currency: str) -> tuple[Decimal | None, str | None]:
    match = _AMOUNT.search(text)
    if match is None:
        return None, None
    amount = Decimal(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        amount *= _THOUSAND
    elif suffix == "m":
        amount *= _MILLION
    currency = default_currency.upper()
    if "ngn" in text or "naira" in text:
        currency = "NGN"
    return amount, currency


def _mentioned_weekday(text: str) -> str | None:
    for name in WEEKDAYS:
        if name in text:
            return name
    return None


def _claim_description(amount: Decimal | None, currency: str | None) -> str:
    if amount is None or currency is None:
        return "Customer claims a payment was sent. The payment is not verified."
    return f"Customer claims they sent {currency} {format(amount, 'f')}. The payment is not verified."


def _commitment_description(amount: Decimal | None, currency: str | None, due_text: str | None) -> str:
    money = "a payment" if amount is None or currency is None else f"{currency} {format(amount, 'f')}"
    when = due_text or "a later date"
    return f"Customer promised to pay {money} on {when}."
