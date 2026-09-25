from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import ActionType, SignalType


@dataclass(frozen=True)
class ActionDraft:
    action_type: str
    title: str
    description: str
    proposed_content: str


def draft_for_signal(
    signal_type: str,
    *,
    customer_name: str | None,
    amount: Decimal | None,
    currency: str | None,
) -> ActionDraft | None:
    """Return a grounded recommendation, or nothing when the signal has no rule.

    Unanswered requests never receive an invented price or availability.
    """
    if signal_type == SignalType.OVERDUE_PAYMENT.value:
        return _overdue_payment(customer_name, amount, currency)
    if signal_type == SignalType.UNANSWERED_REQUEST.value:
        return _unanswered_request(customer_name)
    return None


def _overdue_payment(
    customer_name: str | None,
    amount: Decimal | None,
    currency: str | None,
) -> ActionDraft:
    name = _given_name(customer_name)
    greeting = name or "there"
    if amount is not None and currency:
        money = _money(amount, currency)
        title = f"Follow up with {name} about the overdue {money} payment." if name else "Follow up with customer"
        draft = (
            f"Hi {greeting},\n\n"
            f"Just following up on the {money} payment you mentioned. "
            "Please let us know once the payment has been confirmed.\n\n"
            "Thank you."
        )
    else:
        title = f"Follow up with {name}." if name else "Follow up with customer"
        draft = (
            f"Hi {greeting},\n\n"
            "Just following up on the payment you mentioned. "
            "Please let us know once the payment has been confirmed.\n\n"
            "Thank you."
        )
    return ActionDraft(
        action_type=ActionType.FOLLOW_UP_CUSTOMER.value,
        title=title,
        description="Recommended because this payment commitment is past its due date and remains unfulfilled.",
        proposed_content=draft,
    )


def _unanswered_request(customer_name: str | None) -> ActionDraft:
    name = _given_name(customer_name)
    who = name or "the customer"
    return ActionDraft(
        action_type=ActionType.RESPOND_TO_REQUEST.value,
        title=f"Review {who}'s question and reply yourself." if name else "Review the request and reply yourself.",
        description="Recommended because the customer asked a question and the business has not replied.",
        proposed_content=(
            f"No customer message has been drafted for {who}. "
            "The request asks for information VIGIE does not have, so no price or availability is included. "
            "Review the question and reply yourself."
        ),
    )


def _given_name(customer_name: str | None) -> str | None:
    if customer_name is None:
        return None
    cleaned = customer_name.strip()
    if not cleaned:
        return None
    return cleaned.split()[0]


def _money(amount: Decimal, currency: str) -> str:
    rendered = format(amount.quantize(Decimal("0.01")), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    whole, _, fraction = rendered.partition(".")
    grouped = f"{int(whole):,}"
    if fraction:
        grouped = f"{grouped}.{fraction}"
    if currency == "NGN":
        return f"₦{grouped}"
    return f"{currency} {grouped}"
