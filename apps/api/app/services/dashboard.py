import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.attention import HIGH_PRIORITIES, OPPORTUNITY, classify_attention
from app.domain.enums import CommitmentStatus, SignalStatus
from app.domain.errors import NotFoundError
from app.models import Business, Commitment, Conversation, Customer, Message, Signal
from app.schemas.dashboard import ConversationPreviewRead, DashboardSummaryRead

RECENT_CONVERSATION_LIMIT = 5


def dashboard_summary(session: Session, business_id: uuid.UUID) -> DashboardSummaryRead:
    business = session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    open_signals = list(
        session.scalars(
            select(Signal).where(
                Signal.business_id == business.id,
                Signal.status == SignalStatus.OPEN.value,
            )
        ).all()
    )
    revenue = Decimal("0.00")
    high_priority = 0
    opportunities = 0
    for signal in open_signals:
        if signal.severity in HIGH_PRIORITIES:
            high_priority += 1
        if classify_attention(signal.signal_type, signal.category) == OPPORTUNITY:
            opportunities += 1
        if (
            signal.financial_impact_amount is not None
            and signal.currency == business.default_currency
        ):
            revenue += signal.financial_impact_amount
    missed = int(
        session.scalar(
            select(func.count())
            .select_from(Commitment)
            .where(
                Commitment.business_id == business.id,
                Commitment.status == CommitmentStatus.MISSED.value,
            )
        )
        or 0
    )
    return DashboardSummaryRead(
        business_id=business.id,
        business_name=business.name,
        timezone=business.timezone,
        currency=business.default_currency,
        open_signals=len(open_signals),
        high_priority_signals=high_priority,
        revenue_at_risk=revenue,
        missed_commitments=missed,
        opportunity_signals=opportunities,
        recent_conversations=_recent_conversations(session, business.id),
    )


def _recent_conversations(session: Session, business_id: uuid.UUID) -> list[ConversationPreviewRead]:
    latest = (
        select(
            Message.conversation_id.label("conversation_id"),
            func.max(Message.occurred_at).label("occurred_at"),
        )
        .where(Message.business_id == business_id)
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = session.execute(
        select(Message, Conversation.customer_id, Customer.name)
        .join(
            latest,
            (Message.conversation_id == latest.c.conversation_id)
            & (Message.occurred_at == latest.c.occurred_at),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .outerjoin(
            Customer,
            (Customer.id == Conversation.customer_id) & (Customer.business_id == Conversation.business_id),
        )
        .where(Message.business_id == business_id)
        .order_by(Message.occurred_at.desc(), Message.id.desc())
    ).all()
    previews: list[ConversationPreviewRead] = []
    seen: set[uuid.UUID] = set()
    for message, customer_id, customer_name in rows:
        if message.conversation_id in seen:
            continue
        seen.add(message.conversation_id)
        previews.append(
            ConversationPreviewRead(
                conversation_id=message.conversation_id,
                customer_id=customer_id,
                customer_name=customer_name or "Unknown customer",
                last_message=message.content,
                last_message_at=message.occurred_at,
                sender_type=message.sender_type,
                direction=message.direction,
            )
        )
        if len(previews) == RECENT_CONVERSATION_LIMIT:
            break
    return previews
