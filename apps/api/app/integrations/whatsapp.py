import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.enums import IntegrationProvider, MessageSource, SenderType
from app.domain.errors import AIProviderError, InvalidProposalError, ProviderError
from app.integrations.connections import find_connected_account, mark_sync
from app.integrations.messages import NormalizedMessage
from app.integrations.provider import OutboundDisabled
from app.services.ingestion import ingest_message
from app.services.intake import schedule_message_analysis

logger = logging.getLogger(__name__)


class WhatsAppAdapter:
    provider = IntegrationProvider.WHATSAPP

    def validate_credentials(self, settings: Settings | None = None) -> bool:
        return (settings or get_settings()).whatsapp_configured()

    def get_connection_status(self, settings: Settings | None = None) -> str:
        return "available" if self.validate_credentials(settings) else "not_configured"

    def verify_subscription(self, mode: str | None, token: str | None, challenge: str | None) -> str:
        settings = get_settings()
        expected = settings.meta_verify_token.strip()
        if not expected or mode != "subscribe" or token != expected or not challenge:
            raise ProviderError("Webhook verification failed.")
        return challenge

    def verify_signature(self, body: bytes, header: str | None) -> None:
        secret = get_settings().meta_app_secret.strip()
        if not secret:
            raise ProviderError("Configuration required.")
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        expected = f"sha256={digest}"
        provided = header or ""
        if not hmac.compare_digest(expected, provided):
            raise ProviderError("Invalid signature.")

    def parse_events(self, body: bytes) -> list[dict]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderError("The webhook payload is not valid JSON.") from exc
        if not isinstance(payload, dict):
            return []
        events: list[dict] = []
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if isinstance(value, dict):
                    events.append(value)
        return events

    def normalize_message(self, business_id: uuid.UUID, value: dict) -> list[NormalizedMessage]:
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        phone_number_id = str(metadata.get("phone_number_id") or "").strip()
        names = _contact_names(value.get("contacts"))
        normalized: list[NormalizedMessage] = []
        for item in value.get("messages") or []:
            message = _text_message(business_id, phone_number_id, names, item)
            if message is not None:
                normalized.append(message)
        return normalized

    def send_message(self, recipient: str, text: str) -> None:
        raise OutboundDisabled("Approval records the decision. It does not send a WhatsApp message.")


def receive_whatsapp_events(session: Session, body: bytes) -> dict[str, int]:
    adapter = WhatsAppAdapter()
    received = 0
    stored = 0
    for value in adapter.parse_events(body):
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        phone_number_id = str(metadata.get("phone_number_id") or "").strip()
        connection = find_connected_account(session, IntegrationProvider.WHATSAPP, phone_number_id)
        if connection is None:
            logger.info("Ignored WhatsApp event for an unconnected phone number")
            continue
        for incoming in adapter.normalize_message(connection.business_id, value):
            received += 1
            result = ingest_message(session, incoming)
            if not result.created:
                continue
            stored += 1
            error = None
            try:
                schedule_message_analysis(session, result.message.id, result.message.business_id, incoming.timestamp)
            except (InvalidProposalError, AIProviderError):
                error = "VIGIE could not interpret the latest message."
            mark_sync(session, connection.id, error, failed=False)
            logger.info(
                "Stored WhatsApp message business=%s external_id=%s",
                connection.business_id,
                incoming.external_message_id,
            )
    return {"received": received, "stored": stored}


def _contact_names(contacts: object) -> dict[str, str]:
    names: dict[str, str] = {}
    if not isinstance(contacts, list):
        return names
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        wa_id = str(contact.get("wa_id") or "").strip()
        profile = contact.get("profile") if isinstance(contact.get("profile"), dict) else {}
        name = str(profile.get("name") or "").strip()
        if wa_id and name:
            names[wa_id] = name[:200]
    return names


def _text_message(
    business_id: uuid.UUID,
    phone_number_id: str,
    names: dict[str, str],
    item: object,
) -> NormalizedMessage | None:
    if not isinstance(item, dict) or item.get("type") != "text":
        return None
    text = item.get("text") if isinstance(item.get("text"), dict) else {}
    body = str(text.get("body") or "").strip()
    external_id = str(item.get("id") or "").strip()
    sender = str(item.get("from") or "").strip()
    if not body or not external_id or not sender or not phone_number_id:
        return None
    try:
        occurred_at = datetime.fromtimestamp(int(item.get("timestamp")), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return NormalizedMessage(
        business_id=business_id,
        source=MessageSource.WHATSAPP,
        external_message_id=external_id[:200],
        external_conversation_id=f"wa:{sender}"[:200],
        external_customer_id=sender[:200],
        customer_name=names.get(sender) or f"WhatsApp {sender[-4:]}",
        sender_type=SenderType.CUSTOMER,
        sender_identifier=sender[:200],
        text=body,
        timestamp=occurred_at,
        metadata={"phone_number_id": phone_number_id, "message_type": "text"},
    )
