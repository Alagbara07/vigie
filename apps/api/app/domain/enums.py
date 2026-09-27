from enum import StrEnum


class CustomerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    UNKNOWN = "UNKNOWN"
    INACTIVE = "INACTIVE"


class Channel(StrEnum):
    """Stored as text so a new channel does not require a database enum migration."""

    SIMULATED = "simulated"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    DEMO = "demo"


class MessageSource(StrEnum):
    """Where a normalized message came from. The engine does not branch on this."""

    WHATSAPP = "whatsapp"
    GMAIL = "gmail"
    MICROSOFT365 = "microsoft365"
    DEMO = "demo"


class IntegrationProvider(StrEnum):
    WHATSAPP = "whatsapp"
    GMAIL = "gmail"
    MICROSOFT365 = "microsoft365"
    DEMO = "demo"


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ConversationStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class SenderType(StrEnum):
    CUSTOMER = "customer"
    BUSINESS = "business"
    SYSTEM = "system"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EventType(StrEnum):
    """Detection codes. The database column is varchar, not a PostgreSQL enum."""

    PAYMENT_CLAIM = "PAYMENT_CLAIM"
    PAYMENT_COMMITMENT = "PAYMENT_COMMITMENT"
    NEW_LEAD = "NEW_LEAD"
    PURCHASE_INTENT = "PURCHASE_INTENT"
    HIGH_VALUE_LEAD = "HIGH_VALUE_LEAD"
    CUSTOMER_COMPLAINT = "CUSTOMER_COMPLAINT"
    DELIVERY_ISSUE = "DELIVERY_ISSUE"
    REFUND_REQUEST = "REFUND_REQUEST"
    ORDER_MODIFICATION = "ORDER_MODIFICATION"
    UNANSWERED_REQUEST = "UNANSWERED_REQUEST"
    SUPPLIER_COMMITMENT = "SUPPLIER_COMMITMENT"
    CUSTOMER_COMMITMENT = "CUSTOMER_COMMITMENT"
    EMPLOYEE_COMMITMENT = "EMPLOYEE_COMMITMENT"


class Urgency(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CommitmentType(StrEnum):
    PAYMENT_COMMITMENT = "PAYMENT_COMMITMENT"
    CUSTOMER_COMMITMENT = "CUSTOMER_COMMITMENT"
    SUPPLIER_COMMITMENT = "SUPPLIER_COMMITMENT"
    EMPLOYEE_COMMITMENT = "EMPLOYEE_COMMITMENT"


class CommitmentOwner(StrEnum):
    CUSTOMER = "CUSTOMER"
    BUSINESS = "BUSINESS"
    SUPPLIER = "SUPPLIER"
    EMPLOYEE = "EMPLOYEE"


class CommitmentStatus(StrEnum):
    PENDING = "PENDING"
    FULFILLED = "FULFILLED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


class DuePrecision(StrEnum):
    EXACT = "EXACT"
    DATE = "DATE"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class SignalCategory(StrEnum):
    REVENUE = "REVENUE"
    RISK = "RISK"
    OPERATIONS = "OPERATIONS"
    COMMITMENT = "COMMITMENT"


class SignalType(StrEnum):
    """Attention codes. Revenue-at-risk totals are queries, not a signal type."""

    NEW_LEAD = "NEW_LEAD"
    PURCHASE_INTENT = "PURCHASE_INTENT"
    HIGH_VALUE_LEAD = "HIGH_VALUE_LEAD"
    UPSELL_OPPORTUNITY = "UPSELL_OPPORTUNITY"
    REPEAT_PURCHASE = "REPEAT_PURCHASE"
    PARTNERSHIP_OPPORTUNITY = "PARTNERSHIP_OPPORTUNITY"
    OVERDUE_PAYMENT = "OVERDUE_PAYMENT"
    CUSTOMER_COMPLAINT = "CUSTOMER_COMPLAINT"
    ESCALATION_RISK = "ESCALATION_RISK"
    CHURN_RISK = "CHURN_RISK"
    DELIVERY_ISSUE = "DELIVERY_ISSUE"
    SUSPICIOUS_REQUEST = "SUSPICIOUS_REQUEST"
    NEW_ORDER = "NEW_ORDER"
    ORDER_MODIFICATION = "ORDER_MODIFICATION"
    RETURN_REQUEST = "RETURN_REQUEST"
    REFUND_REQUEST = "REFUND_REQUEST"
    PAYMENT_CLAIM = "PAYMENT_CLAIM"
    APPOINTMENT_REQUEST = "APPOINTMENT_REQUEST"
    UNANSWERED_REQUEST = "UNANSWERED_REQUEST"
    PAYMENT_COMMITMENT = "PAYMENT_COMMITMENT"
    CUSTOMER_COMMITMENT = "CUSTOMER_COMMITMENT"
    SUPPLIER_COMMITMENT = "SUPPLIER_COMMITMENT"
    EMPLOYEE_COMMITMENT = "EMPLOYEE_COMMITMENT"
    MISSED_COMMITMENT = "MISSED_COMMITMENT"


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class ActionType(StrEnum):
    """Recommendation codes. Only some types are produced by current rules."""

    FOLLOW_UP_CUSTOMER = "FOLLOW_UP_CUSTOMER"
    VERIFY_PAYMENT = "VERIFY_PAYMENT"
    RESPOND_TO_REQUEST = "RESPOND_TO_REQUEST"
    REVIEW_DELIVERY = "REVIEW_DELIVERY"
    CONTACT_CUSTOMER = "CONTACT_CUSTOMER"


class ActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
