from typing import Any, Protocol

from app.ai.request import AnalysisRequest


class AIProvider(Protocol):
    """A model adapter. analyze_message returns untrusted structured data, not domain rows."""

    @property
    def name(self) -> str: ...

    def analyze_message(self, request: AnalysisRequest) -> dict[str, Any]: ...
