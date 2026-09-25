import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.enums import Severity, SignalCategory, SignalStatus, SignalType
from app.domain.errors import NotFoundError
from app.schemas.signals import SignalDetailRead, SignalListRead
from app.services.signals import get_signal_detail, list_signal_reads

router = APIRouter(prefix="/api")


@router.get("/signals", response_model=list[SignalListRead])
def get_signals(
    business_id: uuid.UUID,
    status: SignalStatus | None = None,
    signal_type: SignalType | None = None,
    category: SignalCategory | None = None,
    severity: Severity | None = None,
    session: Session = Depends(get_db),
) -> list[SignalListRead]:
    try:
        return list_signal_reads(
            session,
            business_id,
            status=status,
            signal_type=signal_type,
            category=category,
            severity=severity,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/signals/{signal_id}", response_model=SignalDetailRead)
def get_signal_by_id(
    signal_id: uuid.UUID,
    business_id: uuid.UUID = Query(),
    session: Session = Depends(get_db),
) -> SignalDetailRead:
    try:
        return get_signal_detail(session, signal_id, business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
