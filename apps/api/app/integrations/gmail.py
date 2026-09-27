import base64
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.auth.crypto import open_secret
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
from app.models import ChannelConnection, IntegrationCredential
from app.services.ingestion import ingest_message
from app.services.intake import schedule_message_analysis

logger = logging.getLogger(__name__)

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
_LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=10"
_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_PROVIDER_FAILURE = "The provider could not complete the connection."
_SYNC_FAILURE = "VIGIE could not sync Gmail."
_RECONNECT = "Gmail needs to be reconnected."


class HistoryUnavailable(ProviderError):
    """Gmail no longer has changes from the stored history id."""


class GmailAdapter:
    provider = IntegrationProvider.GMAIL

    def validate_credentials(self, settings: Settings | None = None) -> bool:
        return (settings or get_settings()).gmail_configured()

    def get_connection_status(self, settings: Settings | None = None) -> str:
        return "available" if self.validate_credentials(settings) else "not_configured"

    def authorization_url(self, state: str, settings: Settings | None = None) -> str:
        active = settings or get_settings()
        query = urlencode(
            {
                "client_id": active.google_client_id,
                "redirect_uri": active.google_redirect_uri,
                "response_type": "code",
                "scope": _SCOPE,
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "false",
            }
        )
        return f"{_AUTH_URL}?{query}"

    def normalize_message(self, business_id: uuid.UUID, payload: dict) -> NormalizedMessage | None:
        message_id = str(payload.get("id") or "").strip()
        thread_id = str(payload.get("threadId") or message_id).strip()
        headers = _headers(payload.get("payload"))
        name, email = parseaddr(headers.get("from", ""))
        email = email.strip().lower()
        text = _plain_text(payload.get("payload"))
        if not message_id or not email or not text:
            return None
        try:
            occurred_at = datetime.fromtimestamp(int(payload.get("internalDate")) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
        return NormalizedMessage(
            business_id=business_id,
            source=MessageSource.GMAIL,
            external_message_id=message_id[:200],
            external_conversation_id=thread_id[:200],
            external_customer_id=email[:200],
            customer_name=(name.strip() or email)[:200],
            sender_type=SenderType.CUSTOMER,
            sender_identifier=email[:200],
            text=text,
            timestamp=occurred_at,
            metadata={"subject": headers.get("subject"), "thread_id": thread_id, "to": headers.get("to")},
        )

    def send_message(self, recipient: str, text: str) -> None:
        raise OutboundDisabled("Approval records the decision. It does not send an email.")


def complete_gmail_oauth(
    session: Session,
    code: str,
    state: str,
    expected_user_id: uuid.UUID | None = None,
) -> None:
    settings = get_settings()
    if not settings.gmail_configured():
        raise ProviderError("Configuration required.")
    business_id, user_id = consume_oauth_state(
        session,
        state,
        IntegrationProvider.GMAIL,
        expected_user_id,
    )
    tokens = post_form(
        _TOKEN_URL,
        {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ProviderError(_PROVIDER_FAILURE)
    profile = get_json(_PROFILE_URL, access_token)
    email = str(profile.get("emailAddress") or "").strip().lower()
    if not email:
        raise ProviderError(_PROVIDER_FAILURE)
    connection = save_connection(
        session,
        business_id=business_id,
        provider=IntegrationProvider.GMAIL,
        external_account_id=email,
        display_name=email,
        metadata={"scope": _SCOPE},
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
        metadata={"provider": IntegrationProvider.GMAIL.value},
    )
    from app.integrations.gmail_push import prepare_gmail_realtime

    prepare_gmail_realtime(session, business_id)


def sync_gmail(session: Session, business_id: uuid.UUID) -> dict[str, int]:
    connection = require_connected(session, business_id, IntegrationProvider.GMAIL)
    try:
        access_token = access_token_for(session, connection)
    except ProviderError as exc:
        mark_sync(session, connection.id, _token_error(exc), failed=True)
        raise
    try:
        stored = import_recent_messages(session, connection, access_token)
        mark_sync(session, connection.id, None, failed=False)
        logger.info("Synced Gmail business=%s stored=%s", business_id, stored)
        return {"stored": stored}
    except ProviderError:
        mark_sync(session, connection.id, _SYNC_FAILURE, failed=True)
        raise ProviderError(_SYNC_FAILURE) from None
    except (AIProviderError, InvalidProposalError) as exc:
        mark_sync(session, connection.id, "VIGIE could not interpret the latest message.", failed=False)
        raise ProviderError(_SYNC_FAILURE) from exc


def import_recent_messages(session: Session, connection: ChannelConnection, access_token: str) -> int:
    listing = gmail_get(_LIST_URL, access_token)
    messages = listing.get("messages") if isinstance(listing.get("messages"), list) else []
    stored = 0
    for item in messages:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        resource = gmail_get(message_url(str(item["id"])), access_token)
        if _store_gmail_resource(session, connection.business_id, resource):
            stored += 1
    return stored


def access_token_for(session: Session, connection: ChannelConnection) -> str:
    secret = session.get(IntegrationCredential, connection.id)
    token = plaintext_access_token(secret)
    if secret is not None and _token_is_current(secret.expires_at):
        return token
    refresh = open_secret(secret.refresh_token) if secret is not None and secret.refresh_token else None
    if not refresh:
        raise ProviderError(_RECONNECT)
    settings = get_settings()
    tokens = post_form(
        _TOKEN_URL,
        {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
    )
    access = tokens.get("access_token")
    if not isinstance(access, str) or not access:
        raise ProviderError(_RECONNECT)
    rotated = tokens.get("refresh_token")
    store_credential(
        session,
        connection,
        access_token=access,
        refresh_token=rotated if isinstance(rotated, str) and rotated else refresh,
        expires_at=_expiry(tokens.get("expires_in")),
    )
    return access


def gmail_get(url: str, access_token: str) -> dict:
    return _gmail_payload(_gmail_request("GET", url, access_token))


def gmail_post(url: str, access_token: str, payload: dict) -> dict:
    return _gmail_payload(_gmail_request("POST", url, access_token, payload))


def message_url(message_id: str) -> str:
    return f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full"


def _store_gmail_resource(session: Session, business_id: uuid.UUID, resource: dict) -> bool:
    incoming = GmailAdapter().normalize_message(business_id, resource)
    if incoming is None:
        return False
    result = ingest_message(session, incoming)
    if not result.created:
        return False
    schedule_message_analysis(session, result.message.id, business_id, incoming.timestamp)
    return True


def _token_is_current(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc) + timedelta(seconds=60)


def _token_error(exc: ProviderError) -> str:
    if str(exc) == _RECONNECT:
        return _RECONNECT
    return "Configuration required."


def _gmail_request(method: str, url: str, access_token: str, payload: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        with httpx.Client(timeout=20) as client:
            if method == "POST":
                return client.post(url, headers=headers, json=payload or {})
            return client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise ProviderError(_SYNC_FAILURE) from exc


def _gmail_payload(response: httpx.Response) -> dict:
    if response.status_code == 404:
        raise HistoryUnavailable("Gmail history is no longer available.")
    if response.status_code >= 400:
        raise ProviderError(_SYNC_FAILURE)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(_SYNC_FAILURE) from exc
    if not isinstance(payload, dict):
        raise ProviderError(_SYNC_FAILURE)
    return payload


def _headers(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    found: dict[str, str] = {}
    for header in payload.get("headers") or []:
        if not isinstance(header, dict):
            continue
        name = str(header.get("name") or "").strip().lower()
        value = str(header.get("value") or "").strip()
        if name and value:
            found[name] = value
    return found


def _plain_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    direct = _decode(payload.get("body"))
    if direct.strip():
        return _visible_text(direct)
    for part in payload.get("parts") or []:
        if isinstance(part, dict) and part.get("mimeType") == "text/plain":
            text = _decode(part.get("body"))
            if text.strip():
                return _visible_text(text)
    return ""


def _decode(body: object) -> str:
    if not isinstance(body, dict):
        return ""
    data = body.get("data")
    if not isinstance(data, str) or not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""


def _visible_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact


def _expiry(seconds: object) -> datetime:
    try:
        span = int(seconds) if seconds is not None else 3600
    except (TypeError, ValueError):
        span = 3600
    return datetime.now(timezone.utc) + timedelta(seconds=span)
