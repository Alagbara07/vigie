import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.deps import Principal, require_member
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.enums import MessageSource, SenderType
from app.domain.errors import AIProviderError, InvalidProposalError, NotFoundError
from app.integrations.messages import NormalizedMessage, describe_source
from app.schemas.integrations import DemoMessageCreate, DemoMessageListItem, DemoMessageRead
from app.services.ingestion import event_types_for, ingest_message, list_demo_messages
from app.services.intake import schedule_message_analysis

router = APIRouter(prefix="/api")


def require_demo_mode() -> None:
    if not get_settings().vigie_demo_mode:
        raise HTTPException(status_code=404, detail="Not found.")


@router.post("/integrations/demo/messages", response_model=DemoMessageRead)
def post_demo_message(
    payload: DemoMessageCreate,
    _: None = Depends(require_demo_mode),
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> DemoMessageRead:
    del principal
    incoming = NormalizedMessage(
        business_id=payload.business_id,
        source=MessageSource.DEMO,
        external_message_id=payload.external_message_id,
        external_conversation_id=payload.conversation_id,
        customer_name=payload.customer_name,
        sender_type=SenderType.CUSTOMER,
        sender_identifier=payload.customer_name,
        text=payload.text,
        timestamp=payload.timestamp,
    )
    try:
        stored = ingest_message(session, incoming)
        events = event_types_for(session, stored.message)
        analyzed = False
        if stored.created:
            analysis = schedule_message_analysis(
                session,
                stored.message.id,
                stored.message.business_id,
                payload.timestamp,
            )
            events = [event.event_type for event in analysis.events]
            analyzed = True
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidProposalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    label, connection = describe_source(stored.message.source)
    return DemoMessageRead(
        created=stored.created,
        analyzed=analyzed,
        message_id=stored.message.id,
        business_id=stored.message.business_id,
        source=stored.message.source or MessageSource.DEMO.value,
        source_label=label or "WhatsApp Business",
        connection=connection,
        external_message_id=stored.message.external_message_id or payload.external_message_id,
        customer_name=stored.customer_name,
        text=stored.message.content,
        occurred_at=stored.message.occurred_at,
        events=events,
    )


@router.get("/integrations/demo/messages", response_model=list[DemoMessageListItem])
def get_demo_messages(
    business_id: uuid.UUID = Query(),
    _: None = Depends(require_demo_mode),
    principal: Principal = Depends(require_member),
    session: Session = Depends(get_db),
) -> list[DemoMessageListItem]:
    del principal
    try:
        rows = list_demo_messages(session, business_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    items: list[DemoMessageListItem] = []
    for message, customer_name, events in rows:
        label, connection = describe_source(message.source)
        items.append(
            DemoMessageListItem(
                message_id=message.id,
                customer_name=customer_name,
                text=message.content,
                occurred_at=message.occurred_at,
                external_message_id=message.external_message_id or "",
                source_label=label or "WhatsApp Business",
                connection=connection,
                events=events,
            )
        )
    return items
