import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.enums import ActionStatus
from app.domain.errors import ConflictError, NotFoundError
from app.schemas.actions import ActionDecisionRequest, ActionRead, RecommendRead, RecommendRequest
from app.services.actions import approve_action, get_action, list_actions, recommend_actions, reject_action

router = APIRouter(prefix="/api")


@router.post("/actions/recommend", response_model=RecommendRead)
def post_recommend_actions(payload: RecommendRequest, session: Session = Depends(get_db)) -> RecommendRead:
    try:
        return recommend_actions(session, payload.business_id, payload.signal_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/actions", response_model=list[ActionRead])
def get_actions(
    business_id: uuid.UUID,
    status: ActionStatus | None = None,
    signal_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
) -> list[ActionRead]:
    try:
        return list_actions(session, business_id, status=status, signal_id=signal_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/actions/{action_id}", response_model=ActionRead)
def get_action_by_id(
    action_id: uuid.UUID,
    business_id: uuid.UUID = Query(),
    session: Session = Depends(get_db),
) -> ActionRead:
    try:
        return get_action(session, action_id, business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/actions/{action_id}/approve", response_model=ActionRead)
def post_approve_action(
    action_id: uuid.UUID,
    payload: ActionDecisionRequest,
    session: Session = Depends(get_db),
) -> ActionRead:
    return _decide(approve_action, session, action_id, payload)


@router.post("/actions/{action_id}/reject", response_model=ActionRead)
def post_reject_action(
    action_id: uuid.UUID,
    payload: ActionDecisionRequest,
    session: Session = Depends(get_db),
) -> ActionRead:
    return _decide(reject_action, session, action_id, payload)


def _decide(operation, session: Session, action_id: uuid.UUID, payload: ActionDecisionRequest) -> ActionRead:
    try:
        return operation(session, action_id, payload.business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
