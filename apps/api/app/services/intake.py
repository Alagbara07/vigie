import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.factory import build_ai_provider
from app.core.config import Settings, get_settings
from app.services.analysis import analyze_stored_message
from app.schemas.analysis import AnalysisRead


def schedule_message_analysis(
    session: Session,
    message_id: uuid.UUID,
    business_id: uuid.UUID,
    reference_time: datetime | None = None,
    settings: Settings | None = None,
) -> AnalysisRead:
    """Interpret one stored message with the current AI provider.

    Adapters stop after the message is stored. A queue can replace this function
    later without changing WhatsApp, Gmail, or Microsoft code.
    """
    active = settings or get_settings()
    return analyze_stored_message(
        session,
        message_id,
        business_id,
        reference_time,
        build_ai_provider(active),
    )
