import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.errors import ConflictError, NotFoundError
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
def post_business(payload: BusinessCreate, session: Session = Depends(get_db)) -> BusinessRead:
    return _run(lambda: inbox.create_business(session, payload))


@router.get("/businesses", response_model=list[BusinessRead])
def get_businesses(session: Session = Depends(get_db)) -> list[BusinessRead]:
    return inbox.list_businesses(session)


@router.post("/businesses/{business_id}/customers", response_model=CustomerRead, status_code=201)
def post_customer(
    business_id: uuid.UUID,
    payload: CustomerCreate,
    session: Session = Depends(get_db),
) -> CustomerRead:
    return _run(lambda: inbox.create_customer(session, business_id, payload))


@router.get("/businesses/{business_id}/customers", response_model=list[CustomerRead])
def get_customers(business_id: uuid.UUID, session: Session = Depends(get_db)) -> list[CustomerRead]:
    return _run(lambda: inbox.list_customers(session, business_id))


@router.post(
    "/businesses/{business_id}/conversations",
    response_model=ConversationRead,
    status_code=201,
)
def post_conversation(
    business_id: uuid.UUID,
    payload: ConversationCreate,
    session: Session = Depends(get_db),
) -> ConversationRead:
    return _run(lambda: inbox.create_conversation(session, business_id, payload))


@router.get("/businesses/{business_id}/conversations", response_model=list[ConversationRead])
def get_conversations(
    business_id: uuid.UUID,
    session: Session = Depends(get_db),
) -> list[ConversationRead]:
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
    session: Session = Depends(get_db),
) -> MessageRead:
    return _run(lambda: inbox.create_message(session, business_id, conversation_id, payload))


@router.get(
    "/businesses/{business_id}/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
)
def get_messages(
    business_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: Session = Depends(get_db),
) -> list[MessageRead]:
    return _run(lambda: inbox.list_messages(session, business_id, conversation_id))


def _run(action):
    try:
        return action()
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
