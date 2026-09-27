import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.deps import Principal, require_member
from app.core.database import get_db
from app.domain.enums import ActionStatus
from app.domain.errors import ConflictError, NotFoundError
from app.schemas.actions import ActionDecisionRequest, ActionRead, RecommendRead, RecommendRequest
from app.services.actions import approve_action, get_action, list_actions, recommend_actions, reject_action
from app.services.audit import record_audit

router = APIRouter(prefix="/api")


@router.post("/actions/recommend", response_model=RecommendRead)
def post_recommend_actions(
    payload: RecommendRequest,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> RecommendRead:
    del principal
    try:
        return recommend_actions(session, payload.business_id, payload.signal_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/actions", response_model=list[ActionRead])
def get_actions(
    business_id: uuid.UUID,
    status: ActionStatus | None = None,
    signal_id: uuid.UUID | None = None,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> list[ActionRead]:
    del principal
    try:
        return list_actions(session, business_id, status=status, signal_id=signal_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/actions/{action_id}", response_model=ActionRead)
def get_action_by_id(
    action_id: uuid.UUID,
    business_id: uuid.UUID = Query(),
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> ActionRead:
    del principal
    try:
        return get_action(session, action_id, business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/actions/{action_id}/approve", response_model=ActionRead)
def post_approve_action(
    action_id: uuid.UUID,
    payload: ActionDecisionRequest,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> ActionRead:
    result = _decide(lambda: approve_action(session, action_id, payload.business_id, user_id=principal.user.id))
    record_audit(
        session,
        user_id=principal.user.id,
        business_id=payload.business_id,
        action="recommendation_approved",
        resource_type="action",
        resource_id=str(action_id),
    )
    return result


@router.post("/actions/{action_id}/reject", response_model=ActionRead)
def post_reject_action(
    action_id: uuid.UUID,
    payload: ActionDecisionRequest,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> ActionRead:
    del principal
    return _decide(lambda: reject_action(session, action_id, payload.business_id))


def _decide(operation) -> ActionRead:
    try:
        return operation()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
