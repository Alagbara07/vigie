import logging

from app.ai.heuristic import HeuristicAIProvider
from app.ai.nvidia import NvidiaAIProvider
from app.ai.provider import AIProvider
from app.core.config import Settings
from app.domain.errors import AIProviderError
from app.schemas.system import AIProviderStatus

logger = logging.getLogger(__name__)

HEURISTIC_PROVIDER = "heuristic"
NVIDIA_PROVIDER = "nvidia"


def build_ai_provider(settings: Settings) -> AIProvider:
    provider_name = settings.ai_provider.strip().lower()
    if provider_name == HEURISTIC_PROVIDER:
        return HeuristicAIProvider()
    if provider_name == NVIDIA_PROVIDER:
        _require_nvidia(settings)
        return NvidiaAIProvider(
            api_key=settings.nvidia_api_key.strip(),
            model=settings.nvidia_model.strip(),
            base_url=settings.nvidia_base_url.strip(),
            timeout_seconds=settings.nvidia_timeout_seconds,
        )
    raise AIProviderError(f"Unknown AI provider '{settings.ai_provider}'.")


def provider_status(settings: Settings) -> AIProviderStatus:
    provider_name = settings.ai_provider.strip().lower()
    if provider_name == HEURISTIC_PROVIDER:
        return AIProviderStatus(provider=HEURISTIC_PROVIDER, configured=True, model=None)
    if provider_name == NVIDIA_PROVIDER:
        model = settings.nvidia_model.strip() or None
        return AIProviderStatus(provider=NVIDIA_PROVIDER, configured=_nvidia_ready(settings), model=model)
    return AIProviderStatus(provider=settings.ai_provider.strip(), configured=False, model=None)


def _require_nvidia(settings: Settings) -> None:
    missing = _missing_nvidia(settings)
    if settings.nvidia_timeout_seconds <= 0:
        missing.append("NVIDIA_TIMEOUT_SECONDS")
    if not missing:
        return
    logger.warning("NVIDIA provider configuration is incomplete: %s", ", ".join(missing))
    raise AIProviderError("NVIDIA is selected but configuration is missing: " + ", ".join(missing) + ".")


def _nvidia_ready(settings: Settings) -> bool:
    return not _missing_nvidia(settings) and settings.nvidia_timeout_seconds > 0


def _missing_nvidia(settings: Settings) -> list[str]:
    missing: list[str] = []
    if not settings.nvidia_api_key.strip():
        missing.append("NVIDIA_API_KEY")
    if not settings.nvidia_model.strip():
        missing.append("NVIDIA_MODEL")
    if not settings.nvidia_base_url.strip():
        missing.append("NVIDIA_BASE_URL")
    return missing
