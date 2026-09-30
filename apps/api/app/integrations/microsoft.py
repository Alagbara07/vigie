import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.crypto import open_secret
from app.core.config import Settings, get_settings
from app.domain.enums import IntegrationProvider, MessageSource, SenderType
from app.domain.errors import AIProviderError, ConflictError, InvalidProposalError, NotFoundError, ProviderError
from app.integrations.connections import (
    consume_oauth_state,
    mark_sync,
    plaintext_access_token,
    require_connected,
    save_connection,
    store_credential,
)
from app.models import ChannelConnection, IntegrationCredential
from app.services.audit import record_audit
from app.integrations.http_client import get_json, post_form
from app.integrations.oauth_log import log_exception, prefix
from app.integrations.messages import NormalizedMessage
from app.integrations.provider import OutboundDisabled
from app.services.ingestion import ingest_message
from app.services.intake import schedule_message_analysis

logger = logging.getLogger(__name__)

_SCOPE = (
    "openid email offline_access "
    "https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read"
)
_ME_URL = "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName"
_MESSAGES_URL = (
    "https://graph.microsoft.com/v1.0/me/messages"
    "?$top=10&$select=id,conversationId,subject,from,toRecipients,receivedDateTime,body"
)
_PROVIDER_FAILURE = "The provider could not complete the connection."
_RECONNECT = "Microsoft 365 needs to be reconnected."


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
                "redirect_uri": active.resolved_microsoft_redirect_uri(),
                "response_mode": "query",
                "scope": _SCOPE,
                "state": state,
                "prompt": "consent",
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
    _log_redirect(settings)
    if not settings.microsoft_configured():
        logger.warning("%sMicrosoft OAuth callback rejected category=not_configured", prefix())
        raise ProviderError("Configuration required.", reason="finish")
    if not state.strip():
        logger.warning("%sMicrosoft OAuth callback rejected category=state stage=missing", prefix())
        raise ProviderError("Invalid or expired connection attempt.", reason="verify")
    if not code.strip():
        logger.warning("%sMicrosoft OAuth callback rejected category=missing_code", prefix())
        raise ProviderError(_PROVIDER_FAILURE, reason="finish")
    try:
        business_id, user_id = consume_oauth_state(
            session,
            state,
            IntegrationProvider.MICROSOFT365,
            expected_user_id,
        )
    except ProviderError as exc:
        log_exception(logger, "state", exc)
        logger.warning("%sMicrosoft OAuth callback rejected category=state", prefix())
        raise
    logger.info("%sMicrosoft OAuth state accepted business=%s user=%s", prefix(), business_id, user_id)
    logger.info(
        "%sMicrosoft OAuth token exchange started business=%s redirect=%s",
        prefix(),
        business_id,
        settings.resolved_microsoft_redirect_uri(),
    )
    try:
        tokens = post_form(
            f"{_authority(settings)}/token",
            {
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "code": code,
                "redirect_uri": settings.resolved_microsoft_redirect_uri(),
                "grant_type": "authorization_code",
                "scope": _SCOPE,
            },
            purpose="microsoft_token",
        )
    except ProviderError as exc:
        log_exception(logger, "token", exc)
        logger.warning("%sMicrosoft OAuth token exchange failed business=%s category=token", prefix(), business_id)
        raise ProviderError(_PROVIDER_FAILURE, reason="finish") from None
    access_token = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        logger.warning(
            "%sMicrosoft OAuth token exchange failed business=%s category=token access_present=false refresh_present=%s",
            prefix(),
            business_id,
            isinstance(refresh, str) and bool(refresh),
        )
        raise ProviderError(_PROVIDER_FAILURE, reason="finish")
    _log_granted_scopes(tokens, business_id)
    logger.info("%sMicrosoft Graph profile lookup started business=%s", prefix(), business_id)
    try:
        profile = get_json(_ME_URL, access_token, purpose="microsoft_graph_profile")
    except ProviderError as exc:
        log_exception(logger, "profile", exc)
        logger.warning("%sMicrosoft Graph profile lookup failed business=%s category=profile", prefix(), business_id)
        raise ProviderError(_PROVIDER_FAILURE, reason="finish") from None
    mail_value = profile.get("mail")
    upn_value = profile.get("userPrincipalName")
    mail_present = isinstance(mail_value, str) and bool(mail_value.strip())
    upn_present = isinstance(upn_value, str) and bool(upn_value.strip())
    email = str(mail_value or upn_value or "").strip().lower()
    account_id = str(profile.get("id") or email).strip()
    if not email or not account_id:
        logger.warning(
            "%sMicrosoft Graph profile lookup failed business=%s category=mailbox mail_present=%s upn_present=%s",
            prefix(),
            business_id,
            mail_present,
            upn_present,
        )
        raise ProviderError(_PROVIDER_FAILURE, reason="finish")
    logger.info(
        "%sMicrosoft Graph profile lookup succeeded business=%s mail_present=%s upn_present=%s mailbox=present",
        prefix(),
        business_id,
        mail_present,
        upn_present,
    )
    snapshot = _connection_snapshot(session, business_id)
    try:
        connection = save_connection(
            session,
            business_id=business_id,
            provider=IntegrationProvider.MICROSOFT365,
            external_account_id=account_id,
            display_name=email,
            metadata={"mail": email, "profile_name": str(profile.get("displayName") or email).strip(), "scope": _SCOPE},
            connected_by_user_id=user_id,
        )
    except ConflictError as exc:
        log_exception(logger, "conflict", exc)
        logger.warning("%sMicrosoft connection persistence failed business=%s category=conflict", prefix(), business_id)
        raise ProviderError(_PROVIDER_FAILURE, reason="finish") from None
    except NotFoundError as exc:
        log_exception(logger, "missing_business", exc)
        logger.warning(
            "%sMicrosoft connection persistence failed business=%s category=missing_business",
            prefix(),
            business_id,
        )
        raise ProviderError(_PROVIDER_FAILURE, reason="finish") from None
    try:
        store_credential(
            session,
            connection,
            access_token=access_token,
            refresh_token=refresh if isinstance(refresh, str) else None,
            expires_at=_expiry(tokens.get("expires_in")),
        )
    except Exception as exc:
        log_exception(logger, "persist", exc)
        logger.warning("%sMicrosoft connection persistence failed business=%s category=persist", prefix(), business_id)
        _revert_microsoft_connection(session, connection.id, snapshot)
        if isinstance(exc, ProviderError):
            raise ProviderError(str(exc), reason="finish") from exc
        raise ProviderError(_PROVIDER_FAILURE, reason="finish") from exc
    logger.info("%sMicrosoft credential stored business=%s connection=%s", prefix(), business_id, connection.id)
    record_audit(
        session,
        user_id=user_id,
        business_id=business_id,
        action="integration_connected",
        resource_type="integration",
        resource_id=str(connection.id),
        metadata={"provider": IntegrationProvider.MICROSOFT365.value},
    )
    logger.info(
        "%sMicrosoft connection stored business=%s connection=%s status=connected",
        prefix(),
        business_id,
        connection.id,
    )
    from app.integrations.microsoft_push import prepare_microsoft_realtime

    prepare_microsoft_realtime(session, business_id)


def _log_redirect(settings: Settings) -> None:
    uri = settings.resolved_microsoft_redirect_uri()
    host = ""
    path = ""
    if "://" in uri:
        rest = uri.split("://", 1)[1]
        host = rest.split("/", 1)[0].split("@")[-1].split(":", 1)[0].lower()
        path = "/" + rest.split("/", 1)[1] if "/" in rest else ""
    logger.info(
        "%sMicrosoft OAuth redirect scheme_https=%s path_ok=%s trailing_slash=%s local=%s explicit=%s",
        prefix(),
        uri.startswith("https://"),
        path == "/api/integrations/microsoft/callback",
        uri.endswith("/"),
        host in {"localhost", "127.0.0.1", "0.0.0.0"},
        bool(settings.microsoft_redirect_uri.strip()),
    )


def _log_granted_scopes(tokens: dict, business_id: uuid.UUID) -> None:
    raw = tokens.get("scope")
    names: set[str] = set()
    if isinstance(raw, str):
        for part in raw.split():
            name = part.rsplit("/", 1)[-1]
            plain = name.isascii() and name.isidentifier()
            scoped = name.isascii() and "." in name and " " not in name
            if (plain or scoped) and 1 <= len(name) <= 80:
                names.add(name)
    refresh = tokens.get("refresh_token")
    logger.info(
        "%sMicrosoft OAuth token exchange succeeded business=%s scopes=%s refresh_present=%s",
        prefix(),
        business_id,
        ",".join(sorted(names)) if names else "absent",
        isinstance(refresh, str) and bool(refresh),
    )


def _connection_snapshot(session: Session, business_id: uuid.UUID) -> dict | None:
    row = session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.business_id == business_id,
            ChannelConnection.provider == IntegrationProvider.MICROSOFT365.value,
        )
    )
    if row is None:
        return None
    return {
        "status": row.status,
        "external_account_id": row.external_account_id,
        "display_name": row.display_name,
        "connected_at": row.connected_at,
        "connected_by_user_id": row.connected_by_user_id,
        "last_error": row.last_error,
        "connection_metadata": row.connection_metadata,
    }


def _revert_microsoft_connection(session: Session, connection_id: uuid.UUID, snapshot: dict | None) -> None:
    session.rollback()
    row = session.get(ChannelConnection, connection_id)
    if row is None:
        return
    if snapshot is None:
        secret = session.get(IntegrationCredential, row.id)
        if secret is not None:
            session.delete(secret)
        session.delete(row)
    else:
        row.status = snapshot["status"]
        row.external_account_id = snapshot["external_account_id"]
        row.display_name = snapshot["display_name"]
        row.connected_at = snapshot["connected_at"]
        row.connected_by_user_id = snapshot["connected_by_user_id"]
        row.last_error = snapshot["last_error"]
        row.connection_metadata = snapshot["connection_metadata"]
    session.commit()
    logger.info("%sMicrosoft connection persistence rolled back connection=%s", prefix(), connection_id)


def sync_microsoft(session: Session, business_id: uuid.UUID) -> dict[str, int]:
    connection = require_connected(session, business_id, IntegrationProvider.MICROSOFT365)
    try:
        access_token = access_token_for(session, connection)
    except ProviderError as exc:
        message = str(exc) if str(exc) in {_RECONNECT, "Configuration required."} else "VIGIE could not sync Microsoft 365."
        mark_sync(session, connection.id, message, failed=True)
        raise
    try:
        listing = get_json(_MESSAGES_URL, access_token)
        messages = listing.get("value") if isinstance(listing.get("value"), list) else []
        stored = 0
        for item in messages:
            if isinstance(item, dict) and store_microsoft_message(session, business_id, item):
                stored += 1
        mark_sync(session, connection.id, None, failed=False)
        logger.info("Synced Microsoft 365 business=%s stored=%s", business_id, stored)
        return {"stored": stored}
    except ProviderError:
        mark_sync(session, connection.id, "VIGIE could not sync Microsoft 365.", failed=True)
        raise
    except (AIProviderError, InvalidProposalError) as exc:
        mark_sync(session, connection.id, "VIGIE could not interpret the latest message.", failed=False)
        raise ProviderError("VIGIE could not sync Microsoft 365.") from exc


def store_microsoft_message(session: Session, business_id: uuid.UUID, payload: dict) -> bool:
    incoming = MicrosoftAdapter().normalize_message(business_id, payload)
    if incoming is None:
        return False
    result = ingest_message(session, incoming)
    if not result.created:
        return False
    try:
        schedule_message_analysis(session, result.message.id, business_id, incoming.timestamp)
    except (AIProviderError, InvalidProposalError):
        logger.warning("Microsoft message stored but not interpreted business=%s", business_id)
    return True


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
        f"{_authority(settings)}/token",
        {
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
            "scope": _SCOPE,
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


def _token_is_current(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc) + timedelta(seconds=60)


def _expiry(seconds: object) -> datetime:
    try:
        span = int(seconds) if seconds is not None else 3600
    except (TypeError, ValueError):
        span = 3600
    return datetime.now(timezone.utc) + timedelta(seconds=span)
