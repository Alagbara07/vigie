"""Microsoft Graph change notifications.

A notification says a message changed. It is not the email. The message is read
through Graph and stored by the same ingestion path as a manual sync.
"""

import hashlib
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.enums import ConnectionStatus, IntegrationProvider
from app.domain.errors import NotFoundError, ProviderError
from app.integrations.connections import mark_sync, require_connected
from app.integrations.http_client import get_json
from app.integrations.microsoft import access_token_for, store_microsoft_message
from app.integrations.oauth_log import log_exception, prefix
from app.models import ChannelConnection

logger = logging.getLogger(__name__)

_SUBSCRIPTIONS_URL = "https://graph.microsoft.com/v1.0/subscriptions"
_RESOURCE = "me/mailFolders('Inbox')/messages"
_LIFETIME = timedelta(minutes=4000)
# Graph subscriptions last under three days. The renewal job runs once a day,
# so the window has to be longer than the gap between runs.
_RENEW_WITHIN = timedelta(hours=48)
_FAILURE = "Real-time listening could not be enabled."
_RENEW_FAILURE = "Real-time listening could not be renewed."
_NOT_CONFIGURED = "Real-time listening is not configured."
_RECONNECT = "Microsoft 365 needs to be reconnected."
_INVALID = "The Microsoft notification is not valid."


def prepare_microsoft_realtime(session: Session, business_id: uuid.UUID) -> None:
    """Create a Graph subscription after OAuth when the public API URL is HTTPS.

    A subscription failure leaves the mailbox connected. Manual sync still works.
    """
    if not _notifications_configured(get_settings()):
        logger.info(
            "%sMicrosoft subscription skipped stage=subscription_creation result=skipped reason=not_configured business=%s",
            prefix(),
            business_id,
        )
        return
    try:
        register_microsoft_subscription(session, business_id)
        logger.info(
            "%sMicrosoft subscription created stage=subscription_creation result=created business=%s",
            prefix(),
            business_id,
        )
    except NotFoundError:
        raise
    except Exception as exc:
        log_exception(logger, "subscription_creation", exc)
        logger.warning(
            "%sMicrosoft subscription failed stage=subscription_creation result=failed business=%s",
            prefix(),
            business_id,
        )


def register_microsoft_subscription(session: Session, business_id: uuid.UUID) -> ChannelConnection:
    settings = get_settings()
    if not _notifications_configured(settings):
        raise ProviderError(_NOT_CONFIGURED)
    connection = require_connected(session, business_id, IntegrationProvider.MICROSOFT365)
    client_state = secrets.token_urlsafe(32)
    expiration = datetime.now(timezone.utc) + _LIFETIME
    try:
        token = access_token_for(session, connection)
        _delete_existing_subscription(connection, token)
        created = _graph(
            "POST",
            _SUBSCRIPTIONS_URL,
            token,
            {
                "changeType": "created",
                "notificationUrl": _webhook_url(settings),
                "resource": _RESOURCE,
                "expirationDateTime": _stamp(expiration),
                "clientState": client_state,
            },
            purpose="microsoft_subscription",
        )
        subscription_id = str(created.get("id") or "").strip()
        stored_expiration = _parse_time(created.get("expirationDateTime")) or expiration
        if not subscription_id:
            raise ProviderError(_FAILURE)
        _write_metadata(
            session,
            connection,
            subscription_id=subscription_id,
            subscription_expiration=stored_expiration.isoformat(),
            subscription_client_state_hash=_hash_state(client_state),
            subscription_enabled=True,
            subscription_attempted=True,
            subscription_error=None,
        )
        connection.last_error = None
        session.commit()
        logger.info("Registered Microsoft subscription business=%s", business_id)
        return connection
    except ProviderError as exc:
        message = str(exc) if str(exc) in {_RECONNECT, _FAILURE, _NOT_CONFIGURED} else _FAILURE
        _remember_failure_safely(session, connection, message)
        raise ProviderError(message) from None
    except Exception:
        _remember_failure_safely(session, connection, _FAILURE)
        raise ProviderError(_FAILURE) from None


def renew_expiring_microsoft_subscriptions(session: Session, *, now: datetime | None = None) -> int:
    settings = get_settings()
    if not _notifications_configured(settings):
        return 0
    moment = now or datetime.now(timezone.utc)
    window = _RENEW_WITHIN
    rows = session.scalars(
        select(ChannelConnection).where(
            ChannelConnection.provider == IntegrationProvider.MICROSOFT365.value,
            ChannelConnection.status == ConnectionStatus.CONNECTED.value,
        )
    ).all()
    renewed = 0
    for connection in rows:
        expiration = _parse_time(_metadata(connection).get("subscription_expiration"))
        if expiration is None or expiration - moment > window:
            continue
        try:
            _renew_one(session, connection)
            renewed += 1
        except Exception:
            _remember_failure_safely(session, connection, _RENEW_FAILURE)
            logger.info("Microsoft subscription renewal failed business=%s", connection.business_id)
    return renewed


def _delete_existing_subscription(connection: ChannelConnection, access_token: str) -> None:
    subscription_id = str(_metadata(connection).get("subscription_id") or "").strip()
    if not subscription_id:
        return
    try:
        _graph(
            "DELETE",
            f"{_SUBSCRIPTIONS_URL}/{subscription_id}",
            access_token,
            None,
            purpose="microsoft_subscription_delete",
        )
    except ProviderError:
        logger.info("Previous Microsoft subscription was already gone business=%s", connection.business_id)


def stop_microsoft_subscription(session: Session, connection: ChannelConnection) -> None:
    subscription_id = str(_metadata(connection).get("subscription_id") or "").strip()
    if not subscription_id:
        return
    try:
        token = access_token_for(session, connection)
        _graph(
            "DELETE",
            f"{_SUBSCRIPTIONS_URL}/{subscription_id}",
            token,
            None,
            purpose="microsoft_subscription_delete",
        )
        logger.info("Deleted Microsoft subscription business=%s", connection.business_id)
    except ProviderError:
        logger.info("Microsoft subscription delete skipped business=%s", connection.business_id)


def receive_microsoft_notification(session: Session, body: bytes) -> dict[str, int]:
    if len(body) > 1_000_000:
        raise ProviderError(_INVALID)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderError(_INVALID) from exc
    if not isinstance(payload, dict):
        raise ProviderError(_INVALID)
    items = payload.get("value")
    if not isinstance(items, list):
        raise ProviderError(_INVALID)
    stored = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("lifecycleEvent"):
            _apply_lifecycle(session, item)
            continue
        stored += _apply_change(session, item)
    return {"stored": stored}


def validation_token(value: str | None) -> str:
    if not isinstance(value, str):
        raise ProviderError(_INVALID)
    token = value.strip()
    if not token or len(token) > 256 or any(character in token for character in "\r\n"):
        raise ProviderError(_INVALID)
    return token


def microsoft_realtime_fields(row: ChannelConnection | None, settings: Settings) -> dict:
    configured = _notifications_configured(settings)
    fields = {
        "listening": False,
        "realtime": "not_configured" if not configured else "manual",
        "last_notification_at": None,
        "last_error": None if row is None else row.last_error,
        "pubsub_configured": configured,
    }
    if row is None or row.status != ConnectionStatus.CONNECTED.value:
        if row is not None and row.status == ConnectionStatus.ERROR.value and _subscription_needs_recovery(row):
            fields["realtime"] = "needs_attention"
        return fields
    meta = _metadata(row)
    expiration = _parse_time(meta.get("subscription_expiration"))
    fields["last_notification_at"] = _parse_time(meta.get("last_notification_at"))
    now = datetime.now(timezone.utc)
    listening = meta.get("subscription_enabled") is True and expiration is not None and expiration > now
    error = meta.get("subscription_error")
    subscription_error = error if isinstance(error, str) and error.strip() else None
    if listening:
        fields["listening"] = True
        fields["realtime"] = "listening"
        return fields
    expired = expiration is not None and expiration <= now
    if subscription_error or expired or meta.get("subscription_attempted") is True:
        fields["realtime"] = "needs_attention"
        if subscription_error:
            fields["last_error"] = subscription_error
        return fields
    fields["realtime"] = "manual"
    return fields


def _apply_change(session: Session, item: dict) -> int:
    connection = _connection_for_subscription(session, item.get("subscriptionId"))
    if connection is None:
        logger.info("Ignored Microsoft notification for an unknown subscription")
        return 0
    if not _client_state_matches(connection, item.get("clientState")):
        logger.info("Ignored Microsoft notification with an unexpected client state business=%s", connection.business_id)
        return 0
    message_id = _message_id(item)
    if not message_id:
        return 0
    try:
        token = access_token_for(session, connection)
        payload = get_json(_message_url(message_id), token, purpose="microsoft_message")
        created = store_microsoft_message(session, connection.business_id, payload)
    except ProviderError as exc:
        message = _RECONNECT if str(exc) == _RECONNECT else "VIGIE could not sync Microsoft 365."
        mark_sync(session, connection.id, message, failed=True)
        logger.info("Microsoft notification import failed business=%s", connection.business_id)
        return 0
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_error = None
    meta = _metadata(connection)
    meta["last_notification_at"] = datetime.now(timezone.utc).isoformat()
    connection.connection_metadata = meta
    session.commit()
    return 1 if created else 0


def _apply_lifecycle(session: Session, item: dict) -> None:
    connection = _connection_for_subscription(session, item.get("subscriptionId"))
    if connection is None or not _client_state_matches(connection, item.get("clientState")):
        return
    event = str(item.get("lifecycleEvent") or "")
    if event in {"subscriptionRemoved", "reauthorizationRequired", "missed"}:
        _remember_failure(session, connection, _RENEW_FAILURE)
        logger.info("Microsoft subscription lifecycle event=%s business=%s", event, connection.business_id)


def _renew_one(session: Session, connection: ChannelConnection) -> None:
    subscription_id = str(_metadata(connection).get("subscription_id") or "").strip()
    if not subscription_id:
        raise ProviderError(_RENEW_FAILURE)
    token = access_token_for(session, connection)
    expiration = datetime.now(timezone.utc) + _LIFETIME
    updated = _graph(
        "PATCH",
        f"{_SUBSCRIPTIONS_URL}/{subscription_id}",
        token,
        {"expirationDateTime": _stamp(expiration)},
        purpose="microsoft_subscription_renew",
    )
    stored = _parse_time(updated.get("expirationDateTime")) or expiration
    _write_metadata(
        session,
        connection,
        subscription_expiration=stored.isoformat(),
        subscription_enabled=True,
        subscription_attempted=True,
        subscription_error=None,
    )
    connection.last_error = None
    session.commit()
    logger.info("Renewed Microsoft subscription business=%s", connection.business_id)


def _connection_for_subscription(session: Session, subscription_id: object) -> ChannelConnection | None:
    if not isinstance(subscription_id, str) or not subscription_id.strip():
        return None
    rows = session.scalars(
        select(ChannelConnection).where(
            ChannelConnection.provider == IntegrationProvider.MICROSOFT365.value,
            ChannelConnection.status == ConnectionStatus.CONNECTED.value,
        )
    ).all()
    target = subscription_id.strip()
    for row in rows:
        if str(_metadata(row).get("subscription_id") or "") == target:
            return row
    return None


def _client_state_matches(connection: ChannelConnection, presented: object) -> bool:
    if not isinstance(presented, str) or not presented.strip():
        return False
    expected = str(_metadata(connection).get("subscription_client_state_hash") or "")
    return bool(expected) and secrets.compare_digest(expected, _hash_state(presented.strip()))


def _message_id(item: dict) -> str:
    data = item.get("resourceData")
    if isinstance(data, dict) and isinstance(data.get("id"), str) and data["id"].strip():
        return data["id"].strip()
    resource = item.get("resource")
    if isinstance(resource, str) and "/" in resource:
        return resource.rstrip("/").split("/")[-1].strip()
    return ""


def _message_url(message_id: str) -> str:
    select = "id,conversationId,subject,from,toRecipients,receivedDateTime,body"
    return f"https://graph.microsoft.com/v1.0/me/messages/{message_id}?$select={select}"


def _graph(method: str, url: str, access_token: str, payload: dict | None, *, purpose: str) -> dict:
    try:
        request_kwargs: dict = {"headers": {"Authorization": f"Bearer {access_token}"}}
        if payload is not None:
            request_kwargs["json"] = payload
        with httpx.Client(timeout=20) as client:
            response = client.request(method, url, **request_kwargs)
    except httpx.HTTPError:
        logger.warning("Microsoft Graph request failed purpose=%s status=none", purpose)
        raise ProviderError(_FAILURE) from None
    if response.status_code == 404 and method == "DELETE":
        return {}
    if response.status_code >= 400:
        logger.warning(
            "Microsoft Graph request failed purpose=%s status=%s",
            purpose,
            response.status_code,
        )
        raise ProviderError(_FAILURE)
    if response.status_code == 204 or not response.content:
        return {}
    try:
        parsed = response.json()
    except ValueError as exc:
        raise ProviderError(_FAILURE) from exc
    if not isinstance(parsed, dict):
        raise ProviderError(_FAILURE)
    return parsed


def _notifications_configured(settings: Settings) -> bool:
    return settings.api_public_url.strip().startswith("https://")


def _webhook_url(settings: Settings) -> str:
    return settings.api_public_url.strip().rstrip("/") + "/api/integrations/microsoft/webhook"


def _hash_state(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _metadata(connection: ChannelConnection) -> dict:
    raw = connection.connection_metadata
    return dict(raw) if isinstance(raw, dict) else {}


def _write_metadata(session: Session, connection: ChannelConnection, **fields: object) -> None:
    current = session.get(ChannelConnection, connection.id) or connection
    meta = _metadata(current)
    meta.update(fields)
    current.connection_metadata = meta
    session.commit()


def _remember_failure(session: Session, connection: ChannelConnection, message: str) -> None:
    current = session.get(ChannelConnection, connection.id)
    if current is None:
        return
    _write_metadata(
        session,
        current,
        subscription_enabled=False,
        subscription_attempted=True,
        subscription_error=message,
    )


def _remember_failure_safely(session: Session, connection: ChannelConnection, message: str) -> None:
    try:
        _remember_failure(session, connection, message)
    except Exception as exc:
        log_exception(logger, "subscription_creation", exc)
        logger.warning(
            "%sMicrosoft subscription failure was not recorded stage=subscription_creation business=%s",
            prefix(),
            connection.business_id,
        )


def _subscription_needs_recovery(row: ChannelConnection) -> bool:
    meta = _metadata(row)
    if meta.get("subscription_enabled") is True or meta.get("subscription_attempted") is True:
        return True
    error = meta.get("subscription_error")
    return isinstance(error, str) and bool(error.strip())
