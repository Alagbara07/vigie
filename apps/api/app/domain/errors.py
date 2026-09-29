class DomainError(Exception):
    """Base class for expected domain failures."""


class NotFoundError(DomainError):
    """The requested record does not exist in this business."""


class ConflictError(DomainError):
    """The write conflicts with an existing record."""


class InvalidProposalError(DomainError):
    """Structured AI output failed validation and was not persisted."""


class AIProviderError(DomainError):
    """The configured AI provider cannot analyze a message."""


class ProviderError(DomainError):
    """A communication provider could not complete a connection or delivery."""

    def __init__(self, message: str = "", *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason
