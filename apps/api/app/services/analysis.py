import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.dates import ground_relative_due_dates
from app.ai.factory import build_ai_provider
from app.ai.provider import AIProvider
from app.ai.request import AnalysisRequest
from app.core.config import get_settings
from app.domain.errors import InvalidProposalError, NotFoundError
from app.engine.apply import apply_proposal
from app.models import Business, Conversation, Message
from app.schemas.analysis import AnalysisRead, MessageAnalysisProposal

logger = logging.getLogger(__name__)


def analyze_stored_message(
    session: Session,
    message_id: uuid.UUID,
    business_id: uuid.UUID,
    reference_time: datetime | None = None,
    provider: AIProvider | None = None,
) -> AnalysisRead:
    message = session.get(Message, message_id)
    if message is None or message.business_id != business_id:
        raise NotFoundError("Message not found.")
    business = session.get(Business, business_id)
    conversation = session.get(Conversation, message.conversation_id)
    if business is None or conversation is None or conversation.business_id != business_id:
        raise NotFoundError("Message not found.")

    active_provider = provider if provider is not None else build_ai_provider(get_settings())
    resolved_reference = reference_time or message.occurred_at
    request = AnalysisRequest(
        content=message.content,
        occurred_at=message.occurred_at,
        reference_time=resolved_reference,
        timezone_name=business.timezone,
        default_currency=business.default_currency,
    )
    logger.info(
        "Analyzing message %s with provider %s",
        message.id,
        active_provider.name,
    )
    raw_output = active_provider.analyze_message(request)
    proposal = ground_relative_due_dates(
        parse_proposal(raw_output, active_provider.name),
        resolved_reference,
        business.timezone,
    )
    logger.info(
        "Accepted proposal for message %s intent=%s events=%s",
        message.id,
        proposal.intent,
        len(proposal.proposed_events),
    )
    applied = apply_proposal(session, message, conversation, proposal)
    session.commit()
    return AnalysisRead(
        message_id=message.id,
        business_id=business.id,
        provider=active_provider.name,
        proposal=proposal,
        events=applied.events,
        commitments=applied.commitments,
    )


def parse_proposal(raw_output: Any, provider_name: str) -> MessageAnalysisProposal:
    if isinstance(raw_output, MessageAnalysisProposal):
        raw_output = raw_output.model_dump(mode="json")
    try:
        proposal = MessageAnalysisProposal.model_validate(raw_output)
    except ValidationError as exc:
        logger.warning("Rejected malformed AI output from provider %s", provider_name)
        raise InvalidProposalError("The AI proposal was rejected because it is not valid structured output.") from exc
    if proposal.provider != provider_name:
        logger.warning(
            "Rejected AI output whose provider label %s does not match %s",
            proposal.provider,
            provider_name,
        )
        raise InvalidProposalError("The AI proposal was rejected because its provider label does not match.")
    return proposal
