from typing import Protocol

from app.domain.enums import IntegrationProvider
from app.integrations.messages import NormalizedMessage


class OutboundDisabled(Exception):
    """Approval records a decision. It does not send a customer message."""


class CommunicationProvider(Protocol):
    """Provider-specific connection and payload handling. The engine never calls these directly."""

    provider: IntegrationProvider

    def validate_credentials(self) -> bool: ...

    def get_connection_status(self) -> str: ...

    def normalize_message(self, payload: dict) -> NormalizedMessage | None: ...

    def send_message(self, recipient: str, text: str) -> None: ...
