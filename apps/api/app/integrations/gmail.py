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
_SCOPE = "openid email profile https://www.googleapis.com/auth/gmail.readonly"
_PROVIDER_FAILURE = "The provider could not complete the connection."
_SYNC_FAILURE = "VIGIE could not sync Gmail."
_RECONNECT = "Gmail needs to be reconnected."


class HistoryUnavailable(ProviderError):
    """Gmail no longer has changes from the stored history id."""


class GmailUnauthorized(ProviderError):
    """Gmail rejected the access token. A stored refresh token may still be valid."""

    def __init__(self) -> None:
        super().__init__(_RECONNECT)


class GmailNotFound(ProviderError):
    def __init__(self) -> None:
        super().__init__("Gmail message is no longer available.")


class GmailForbidden(ProviderError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(_RECONNECT if reason in _SCOPE_REASONS else _SYNC_FAILURE)


_SCOPE_REASONS = {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}


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
                "redirect_uri": active.resolved_google_redirect_uri(),
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
        text = _plain_text(payload.get("payload")) or _visible_text(str(payload.get("snippet") or ""))
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
            "redirect_uri": settings.resolved_google_redirect_uri(),
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
    except ProviderError as exc:
        reconnect = str(exc) == _RECONNECT
        mark_sync(session, connection.id, _RECONNECT if reconnect else _SYNC_FAILURE, failed=reconnect)
        logger.warning(
            "Gmail sync failed business=%s stage=import category=%s",
            business_id,
            "reconnect" if reconnect else "provider",
        )
        raise ProviderError(_RECONNECT if reconnect else _SYNC_FAILURE) from None
    except (AIProviderError, InvalidProposalError):
        mark_sync(session, connection.id, "VIGIE could not interpret the latest message.", failed=False)
        logger.warning("Gmail sync failed business=%s stage=analysis category=interpretation", business_id)
        raise ProviderError(_SYNC_FAILURE) from None


def import_recent_messages(session: Session, connection: ChannelConnection, access_token: str) -> int:
    holder = {"token": access_token}

    def fetch(url: str) -> dict:
        try:
            return gmail_get(url, holder["token"])
        except GmailUnauthorized:
            logger.info("Gmail access token was rejected; refreshing business=%s", connection.business_id)
            holder["token"] = access_token_for(session, connection, force_refresh=True)
            return gmail_get(url, holder["token"])

    listing = fetch(_LIST_URL)
    messages = listing.get("messages") if isinstance(listing.get("messages"), list) else []
    stored = 0
    for item in messages:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            resource = _read_message(fetch, str(item["id"]))
        except GmailNotFound:
            logger.info("Gmail sync skipped a missing message business=%s", connection.business_id)
            continue
        except GmailForbidden as exc:
            if exc.reason in _SCOPE_REASONS:
                raise ProviderError(_RECONNECT) from None
            logger.warning(
                "Gmail sync skipped a message business=%s stage=message reason=%s",
                connection.business_id,
                exc.reason,
            )
            continue
        if _store_gmail_resource(session, connection.business_id, resource):
            stored += 1
    return stored


def access_token_for(session: Session, connection: ChannelConnection, *, force_refresh: bool = False) -> str:
    secret = session.get(IntegrationCredential, connection.id)
    token = plaintext_access_token(secret)
    if not force_refresh and secret is not None and _token_is_current(secret.expires_at):
        return token
    refresh = open_secret(secret.refresh_token) if secret is not None and secret.refresh_token else None
    if not refresh:
        raise ProviderError(_RECONNECT)
    settings = get_settings()
    try:
        tokens = post_form(
            _TOKEN_URL,
            {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
    except ProviderError as exc:
        raise ProviderError(_RECONNECT) from exc
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
    try:
        schedule_message_analysis(session, result.message.id, business_id, incoming.timestamp)
    except (AIProviderError, InvalidProposalError):
        logger.warning("Gmail message stored but not interpreted business=%s stage=analysis", business_id)
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
    if response.status_code == 404 and "/history" in str(response.request.url):
        raise HistoryUnavailable("Gmail history is no longer available.")
    if response.status_code == 404:
        raise GmailNotFound()
    if response.status_code == 401:
        status, reason = _google_failure(response)
        logger.warning("Gmail request rejected status=%s reason=%s stage=auth", status, reason)
        raise GmailUnauthorized()
    if response.status_code == 403:
        status, reason = _google_failure(response)
        logger.warning("Gmail request rejected status=%s reason=%s stage=permission", status, reason)
        raise GmailForbidden(reason)
    if response.status_code >= 400:
        status, reason = _google_failure(response)
        logger.warning("Gmail request rejected status=%s reason=%s stage=provider", status, reason)
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


def _read_message(fetch, message_id: str) -> dict:
    try:
        return fetch(message_url(message_id))
    except GmailForbidden as exc:
        if exc.reason not in _SCOPE_REASONS:
            raise
        logger.warning("Gmail full message unavailable reason=%s", exc.reason)
        return fetch(_metadata_url(message_id))


def _metadata_url(message_id: str) -> str:
    return (
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
        f"{message_id}?format=metadata&metadataHeaders=From&metadataHeaders=To&metadataHeaders=Subject"
    )


def _google_failure(response: httpx.Response) -> tuple[int, str]:
    reason = "unknown"
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            errors = error.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                raw = errors[0].get("reason")
                if isinstance(raw, str) and raw.strip():
                    reason = raw.strip()
            elif isinstance(error.get("status"), str) and error.get("status").strip():
                reason = error["status"].strip()
        elif error in {"invalid_grant", "invalid_client", "unauthorized_client"}:
            reason = str(error)
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "", reason)[:80]
    return response.status_code, cleaned or "unknown"


def _plain_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    plain = _find_part(payload, "text/plain")
    if plain:
        return _visible_text(plain)
    html = _find_part(payload, "text/html")
    if html:
        return _visible_text(re.sub(r"<[^>]+>", " ", html))
    return ""


def _find_part(payload: dict, mime_type: str) -> str:
    mime = str(payload.get("mimeType") or "")
    if mime.startswith(mime_type):
        text = _decode(payload.get("body")).strip()
        if text:
            return text
    for part in payload.get("parts") or []:
        if isinstance(part, dict):
            found = _find_part(part, mime_type)
            if found:
                return found
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
