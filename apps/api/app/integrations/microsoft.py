import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.enums import IntegrationProvider, MessageSource, SenderType
from app.domain.errors import AIProviderError, InvalidProposalError, ProviderError
from app.integrations.connections import (
    consume_oauth_state,
    mark_sync,
    plaintext_access_token,
    require_connected,
    save_connection,
    store_credential,
)
from app.services.audit import record_audit
from app.integrations.http_client import get_json, post_form
from app.integrations.messages import NormalizedMessage
from app.integrations.provider import OutboundDisabled
from app.models import IntegrationCredential
from app.services.ingestion import ingest_message
from app.services.intake import schedule_message_analysis

logger = logging.getLogger(__name__)

_SCOPE = "offline_access https://graph.microsoft.com/Mail.Read"
_ME_URL = "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName"
_MESSAGES_URL = (
    "https://graph.microsoft.com/v1.0/me/messages"
    "?$top=10&$select=id,conversationId,subject,from,toRecipients,receivedDateTime,body"
)
_PROVIDER_FAILURE = "The provider could not complete the connection."


class MicrosoftAdapter:
    provider = IntegrationProvider.MICROSOFT365

    def validate_credentials(self, settings: Settings | None = None) -> bool:
        return (settings or get_settings()).microsoft_configured()

    def get_connection_status(self, settings: Settings | None = None) -> str:
        return "available" if self.validate_credentials(settings) else "not_configured"

    def authorization_url(self, state: str, settings: Settings | None = None) -> str:
        active = settings or get_settings()
        query = urlencode(
            {
                "client_id": active.microsoft_client_id,
                "response_type": "code",
                "redirect_uri": active.microsoft_redirect_uri,
                "response_mode": "query",
                "scope": _SCOPE,
                "state": state,
            }
        )
        return f"{_authority(active)}/authorize?{query}"

    def normalize_message(self, business_id: uuid.UUID, payload: dict) -> NormalizedMessage | None:
        message_id = str(payload.get("id") or "").strip()
        conversation_id = str(payload.get("conversationId") or message_id).strip()
        sender = payload.get("from") if isinstance(payload.get("from"), dict) else {}
        address = sender.get("emailAddress") if isinstance(sender.get("emailAddress"), dict) else {}
        email = str(address.get("address") or "").strip().lower()
        name = str(address.get("name") or "").strip()
        body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
        text = _visible_text(str(body.get("content") or ""))
        if not message_id or not email or not text:
            return None
        occurred_at = _received(payload.get("receivedDateTime"))
        if occurred_at is None:
            return None
        recipients = payload.get("toRecipients") if isinstance(payload.get("toRecipients"), list) else []
        return NormalizedMessage(
            business_id=business_id,
            source=MessageSource.MICROSOFT365,
            external_message_id=message_id[:200],
            external_conversation_id=conversation_id[:200],
            external_customer_id=email[:200],
            customer_name=(name or email)[:200],
            sender_type=SenderType.CUSTOMER,
            sender_identifier=email[:200],
            text=text,
            timestamp=occurred_at,
            metadata={
                "subject": payload.get("subject"),
                "conversation_id": conversation_id,
                "to": _recipient(recipients),
            },
        )

    def send_message(self, recipient: str, text: str) -> None:
        raise OutboundDisabled("Approval records the decision. It does not send an email.")


def complete_microsoft_oauth(
    session: Session,
    code: str,
    state: str,
    expected_user_id: uuid.UUID | None = None,
) -> None:
    settings = get_settings()
    if not settings.microsoft_configured():
        raise ProviderError("Configuration required.")
    business_id, user_id = consume_oauth_state(
        session,
        state,
        IntegrationProvider.MICROSOFT365,
        expected_user_id,
    )
    tokens = post_form(
        f"{_authority(settings)}/token",
        {
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "code": code,
            "redirect_uri": settings.microsoft_redirect_uri,
            "grant_type": "authorization_code",
            "scope": _SCOPE,
        },
    )
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ProviderError(_PROVIDER_FAILURE)
    profile = get_json(_ME_URL, access_token)
    email = str(profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
    account_id = str(profile.get("id") or email).strip()
    if not email or not account_id:
        raise ProviderError(_PROVIDER_FAILURE)
    display = str(profile.get("displayName") or email).strip()
    connection = save_connection(
        session,
        business_id=business_id,
        provider=IntegrationProvider.MICROSOFT365,
        external_account_id=account_id,
        display_name=display,
        metadata={"mail": email, "scope": _SCOPE},
        connected_by_user_id=user_id,
    )
    refresh = tokens.get("refresh_token")
    store_credential(
        session,
        connection,
        access_token=access_token,
        refresh_token=refresh if isinstance(refresh, str) else None,
        expires_at=_expiry(tokens.get("expires_in")),
    )
    record_audit(
        session,
        user_id=user_id,
        business_id=business_id,
        action="integration_connected",
        resource_type="integration",
        resource_id=str(connection.id),
        metadata={"provider": IntegrationProvider.MICROSOFT365.value},
    )


def sync_microsoft(session: Session, business_id: uuid.UUID) -> dict[str, int]:
    connection = require_connected(session, business_id, IntegrationProvider.MICROSOFT365)
    secret = session.get(IntegrationCredential, connection.id)
    try:
        access_token = plaintext_access_token(secret)
    except ProviderError:
        mark_sync(session, connection.id, "Configuration required.", failed=True)
        raise
    try:
        listing = get_json(_MESSAGES_URL, access_token)
        messages = listing.get("value") if isinstance(listing.get("value"), list) else []
        stored = 0
        for item in messages:
            if not isinstance(item, dict):
                continue
            incoming = MicrosoftAdapter().normalize_message(business_id, item)
            if incoming is None:
                continue
            result = ingest_message(session, incoming)
            if not result.created:
                continue
            stored += 1
            schedule_message_analysis(session, result.message.id, business_id, incoming.timestamp)
        mark_sync(session, connection.id, None, failed=False)
        logger.info("Synced Microsoft 365 business=%s stored=%s", business_id, stored)
        return {"stored": stored}
    except ProviderError:
        mark_sync(session, connection.id, "VIGIE could not sync Microsoft 365.", failed=True)
        raise
    except (AIProviderError, InvalidProposalError) as exc:
        mark_sync(session, connection.id, "VIGIE could not interpret the latest message.", failed=False)
        raise ProviderError("VIGIE could not sync Microsoft 365.") from exc


def _authority(settings: Settings) -> str:
    tenant = settings.microsoft_tenant_id.strip() or "common"
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"


def _received(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _recipient(recipients: list) -> str | None:
    if not recipients or not isinstance(recipients[0], dict):
        return None
    address = recipients[0].get("emailAddress")
    if not isinstance(address, dict):
        return None
    email = str(address.get("address") or "").strip()
    return email or None


def _visible_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", without_tags).strip()


def _expiry(seconds: object) -> datetime:
    try:
        span = int(seconds) if seconds is not None else 3600
    except (TypeError, ValueError):
        span = 3600
    return datetime.now(timezone.utc) + timedelta(seconds=span)
