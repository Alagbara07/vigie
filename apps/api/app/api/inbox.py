import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth.access import ensure_membership, memberships_for
from app.auth.cookies import set_business_cookie
from app.auth.deps import Principal, require_member, require_user
from app.core.database import get_db
from app.domain.enums import MemberRole
from app.domain.errors import ConflictError, NotFoundError
from app.services.audit import record_audit
from app.schemas.inbox import (
    BusinessCreate,
    BusinessRead,
    ConversationCreate,
    ConversationRead,
    CustomerCreate,
    CustomerRead,
    MessageCreate,
    MessageRead,
)
from app.services import inbox

router = APIRouter(prefix="/api")


@router.post("/businesses", response_model=BusinessRead, status_code=201)
def post_business(
    payload: BusinessCreate,
    response: Response,
    principal: Principal = Depends(require_user),
    session: Session = Depends(get_db),
) -> BusinessRead:
    business = _run(lambda: inbox.create_business(session, payload))
    ensure_membership(session, principal.user.id, business.id, MemberRole.OWNER)
    record_audit(
        session,
        user_id=principal.user.id,
        business_id=business.id,
        action="business_created",
        resource_type="business",
        resource_id=str(business.id),
    )
    set_business_cookie(response, str(business.id))
    return business


@router.get("/businesses", response_model=list[BusinessRead])
def get_businesses(
    principal: Principal = Depends(require_user),
    session: Session = Depends(get_db),
) -> list[BusinessRead]:
    return [business for business, _membership in memberships_for(session, principal.user.id)]


@router.post("/businesses/{business_id}/customers", response_model=CustomerRead, status_code=201)
def post_customer(
    business_id: uuid.UUID,
    payload: CustomerCreate,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> CustomerRead:
    del principal
    return _run(lambda: inbox.create_customer(session, business_id, payload))


@router.get("/businesses/{business_id}/customers", response_model=list[CustomerRead])
def get_customers(
    business_id: uuid.UUID,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> list[CustomerRead]:
    del principal
    return _run(lambda: inbox.list_customers(session, business_id))


@router.post(
    "/businesses/{business_id}/conversations",
    response_model=ConversationRead,
    status_code=201,
)
def post_conversation(
    business_id: uuid.UUID,
    payload: ConversationCreate,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> ConversationRead:
    del principal
    return _run(lambda: inbox.create_conversation(session, business_id, payload))


@router.get("/businesses/{business_id}/conversations", response_model=list[ConversationRead])
def get_conversations(
    business_id: uuid.UUID,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> list[ConversationRead]:
    del principal
    return _run(lambda: inbox.list_conversations(session, business_id))


@router.post(
    "/businesses/{business_id}/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=201,
)
def post_message(
    business_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> MessageRead:
    del principal
    return _run(lambda: inbox.create_message(session, business_id, conversation_id, payload))


@router.get(
    "/businesses/{business_id}/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
)
def get_messages(
    business_id: uuid.UUID,
    conversation_id: uuid.UUID,
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> list[MessageRead]:
    del principal
    return _run(lambda: inbox.list_messages(session, business_id, conversation_id))


def _run(action):
    try:
        return action()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
