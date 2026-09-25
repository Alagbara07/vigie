import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.factory import build_ai_provider
from app.ai.provider import AIProvider
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.errors import AIProviderError, InvalidProposalError, NotFoundError
from app.schemas.analysis import AnalysisRead, AnalyzeMessageRequest
from app.services.analysis import analyze_stored_message

router = APIRouter(prefix="/api")


def get_configured_provider() -> AIProvider:
    try:
        return build_ai_provider(get_settings())
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/messages/{message_id}/analyze", response_model=AnalysisRead)
def post_analyze_message(
    message_id: uuid.UUID,
    payload: AnalyzeMessageRequest,
    session: Session = Depends(get_db),
    provider: AIProvider = Depends(get_configured_provider),
) -> AnalysisRead:
    try:
        return analyze_stored_message(
            session,
            message_id,
            payload.business_id,
            payload.reference_time,
            provider,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidProposalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
