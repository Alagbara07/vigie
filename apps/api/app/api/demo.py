from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.factory import build_ai_provider
from app.auth.access import ensure_membership, role_for
from app.auth.deps import Principal, require_user
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.enums import MemberRole
from app.domain.errors import AIProviderError, InvalidProposalError, NotFoundError
from app.models import Business
from app.seed.demo import DEMO_SLUG
from app.schemas.demo import DemoResetRead, DemoRunRead
from app.services.demo import reset_demo, run_demo

router = APIRouter(prefix="/api")


def _require_existing_demo_membership(session: Session, principal: Principal) -> None:
    business = session.scalar(select(Business).where(Business.slug == DEMO_SLUG))
    if business is not None and role_for(session, principal.user.id, business.id) is None:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")


def _own_demo_business(session: Session, principal: Principal) -> None:
    business = session.scalar(select(Business).where(Business.slug == DEMO_SLUG))
    if business is not None:
        ensure_membership(session, principal.user.id, business.id, MemberRole.OWNER)


def require_demo_mode() -> None:
    if not get_settings().vigie_demo_mode:
        raise HTTPException(status_code=404, detail="Not found.")


@router.post("/demo/reset", response_model=DemoResetRead)
def post_demo_reset(
    _: None = Depends(require_demo_mode),
    principal: Principal = Depends(require_user),
    session: Session = Depends(get_db),
) -> DemoResetRead:
    _require_existing_demo_membership(session, principal)
    result = reset_demo(session)
    _own_demo_business(session, principal)
    return result


@router.post("/demo/run", response_model=DemoRunRead)
def post_demo_run(
    _: None = Depends(require_demo_mode),
    principal: Principal = Depends(require_user),
    session: Session = Depends(get_db),
) -> DemoRunRead:
    _require_existing_demo_membership(session, principal)
    try:
        provider = build_ai_provider(get_settings())
        result = run_demo(session, provider)
        _own_demo_business(session, principal)
        return result
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidProposalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
