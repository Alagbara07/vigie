from fastapi import APIRouter

from app.ai.factory import provider_status
from app.core.config import get_settings
from app.schemas.demo import DemoModeRead
from app.schemas.system import AIProviderStatus

router = APIRouter(prefix="/api")


@router.get("/system/ai-provider", response_model=AIProviderStatus)
def get_ai_provider_status() -> AIProviderStatus:
    return provider_status(get_settings())


@router.get("/system/demo", response_model=DemoModeRead)
def get_demo_mode() -> DemoModeRead:
    return DemoModeRead(enabled=get_settings().vigie_demo_mode)
