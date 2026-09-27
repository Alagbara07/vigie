"""Import models so Alembic and the application share one metadata registry."""

from app.models.base import Base
from app.models.domain import (
    Action,
    AuditEvent,
    Business,
    BusinessEvent,
    ChannelConnection,
    Commitment,
    Conversation,
    Customer,
    IntegrationCredential,
    Membership,
    Message,
    OAuthState,
    Signal,
    User,
    UserSession,
)

__all__ = [
    "Action",
    "AuditEvent",
    "Base",
    "Business",
    "BusinessEvent",
    "ChannelConnection",
    "Commitment",
    "Conversation",
    "Customer",
    "IntegrationCredential",
    "Membership",
    "Message",
    "OAuthState",
    "Signal",
    "User",
    "UserSession",
]
