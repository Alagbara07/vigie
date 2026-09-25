from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.factory import build_ai_provider
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.errors import AIProviderError, InvalidProposalError, NotFoundError
from app.schemas.demo import DemoResetRead, DemoRunRead
from app.services.demo import reset_demo, run_demo

router = APIRouter(prefix="/api")


def require_demo_mode() -> None:
    if not get_settings().vigie_demo_mode:
        raise HTTPException(status_code=404, detail="Not found.")


@router.post("/demo/reset", response_model=DemoResetRead)
def post_demo_reset(
    _: None = Depends(require_demo_mode),
    session: Session = Depends(get_db),
) -> DemoResetRead:
    return reset_demo(session)


@router.post("/demo/run", response_model=DemoRunRead)
def post_demo_run(
    _: None = Depends(require_demo_mode),
    session: Session = Depends(get_db),
) -> DemoRunRead:
    try:
        provider = build_ai_provider(get_settings())
        return run_demo(session, provider)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidProposalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
