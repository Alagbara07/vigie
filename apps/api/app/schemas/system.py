from pydantic import BaseModel


class AIProviderStatus(BaseModel):
    provider: str
    configured: bool
    model: str | None = None
