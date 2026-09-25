from app.domain.enums import Severity, SignalCategory, SignalType

OPPORTUNITY = "opportunity"
OPERATIONS = "operations"
RISK = "risk"

OPPORTUNITY_SIGNAL_TYPES = frozenset(
    {
        SignalType.NEW_LEAD.value,
        SignalType.PURCHASE_INTENT.value,
        SignalType.HIGH_VALUE_LEAD.value,
        SignalType.UPSELL_OPPORTUNITY.value,
        SignalType.REPEAT_PURCHASE.value,
        SignalType.PARTNERSHIP_OPPORTUNITY.value,
    }
)

OPERATIONS_SIGNAL_TYPES = frozenset(
    {
        SignalType.UNANSWERED_REQUEST.value,
        SignalType.DELIVERY_ISSUE.value,
        SignalType.NEW_ORDER.value,
        SignalType.ORDER_MODIFICATION.value,
        SignalType.APPOINTMENT_REQUEST.value,
        SignalType.RETURN_REQUEST.value,
        SignalType.REFUND_REQUEST.value,
    }
)

HIGH_PRIORITIES = frozenset({Severity.HIGH.value, Severity.CRITICAL.value})


def classify_attention(signal_type: str, category: str) -> str:
    """Group a signal for the command center.

    Opportunity types stay opportunities. Operations are operational work.
    Everything else, including overdue payment, is a risk. The frontend does
    not repeat this rule.
    """
    if signal_type in OPPORTUNITY_SIGNAL_TYPES:
        return OPPORTUNITY
    if category == SignalCategory.OPERATIONS.value or signal_type in OPERATIONS_SIGNAL_TYPES:
        return OPERATIONS
    return RISK
