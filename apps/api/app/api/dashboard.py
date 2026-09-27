import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import Principal, require_member
from app.core.database import get_db
from app.domain.errors import NotFoundError
from app.schemas.dashboard import DashboardSummaryRead
from app.services.dashboard import dashboard_summary

router = APIRouter(prefix="/api")


@router.get("/dashboard/summary", response_model=DashboardSummaryRead)
def get_dashboard_summary(
    business_id: uuid.UUID,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> DashboardSummaryRead:
    del principal
    try:
        return dashboard_summary(session, business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
