"""Gmail watch, history, and Pub/Sub push.

A notification says the mailbox changed. It is not the email. Changed messages
are read through the Gmail API and stored by the existing ingestion path.
"""

import base64
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.enums import ConnectionStatus, IntegrationProvider
from app.domain.errors import ProviderError
from app.integrations.connections import find_connected_account, require_connected
from app.integrations.gmail import (
    HistoryUnavailable,
    _PROFILE_URL,
    access_token_for,
    gmail_get,
    gmail_post,
    import_recent_messages,
    message_url,
)
from app.integrations.gmail import _store_gmail_resource
from app.models import ChannelConnection

logger = logging.getLogger(__name__)

_WATCH_URL = "https://gmail.googleapis.com/gmail/v1/users/me/watch"
_HISTORY_URL = "https://gmail.googleapis.com/gmail/v1/users/me/history"
_INVALID = "The Pub/Sub payload is not valid."
_SYNC_FAILURE = "VIGIE could not sync Gmail."
_WATCH_FAILURE = "Real-time listening could not be enabled."
_RENEW_FAILURE = "Real-time listening could not be renewed."
_NOT_CONFIGURED = "Real-time listening is not configured."
_RECONNECT = "Gmail needs to be reconnected."
_MAX_HISTORY_PAGES = 20


def stop_gmail_watch(session: Session, connection: ChannelConnection) -> None:
    if _metadata(connection).get("watch_enabled") is not True and not _metadata(connection).get("watch_expiration"):
        return
    try:
        token = access_token_for(session, connection)
        gmail_post("https://gmail.googleapis.com/gmail/v1/users/me/stop", token, {})
        logger.info("Stopped Gmail watch business=%s", connection.business_id)
    except ProviderError:
        logger.info("Gmail watch stop skipped business=%s", connection.business_id)


def prepare_gmail_realtime(session: Session, business_id: uuid.UUID) -> None:
    """Register a watch after OAuth when Pub/Sub is configured.

    A watch failure leaves the mailbox connected. Manual sync still works.
    """
    if not get_settings().gmail_pubsub_configured():
        return
    try:
        register_gmail_watch(session, business_id)
    except ProviderError:
        logger.info("Gmail connected without real-time listening business=%s", business_id)


def register_gmail_watch(session: Session, business_id: uuid.UUID) -> ChannelConnection:
    settings = get_settings()
    if not settings.gmail_pubsub_configured():
        raise ProviderError(_NOT_CONFIGURED)
    connection = require_connected(session, business_id, IntegrationProvider.GMAIL)
    try:
        token = access_token_for(session, connection)
        profile = gmail_get(_PROFILE_URL, token)
        baseline = str(profile.get("historyId") or "").strip()
        if not baseline:
            raise ProviderError(_WATCH_FAILURE)
        _write_metadata(session, connection, history_id=baseline)
        try:
            import_recent_messages(session, connection, token)
        except ProviderError:
            _restore_connected(session, connection.id)
        token = access_token_for(session, connection)
        watched = gmail_post(
            _WATCH_URL,
            token,
            {"topicName": settings.gmail_pubsub_topic.strip(), "labelIds": ["INBOX"]},
        )
        expiration = _millis(watched.get("expiration"))
        if expiration is None:
            raise ProviderError(_WATCH_FAILURE)
        watch_history = str(watched.get("historyId") or baseline).strip() or baseline
        apply_gmail_history(session, connection, baseline)
        connection = session.get(ChannelConnection, connection.id) or connection
        stored_history = str(_metadata(connection).get("history_id") or baseline)
        _write_metadata(
            session,
            connection,
            history_id=_later_history(stored_history, watch_history),
            watch_enabled=True,
            watch_expiration=expiration.isoformat(),
            pubsub_topic=settings.gmail_pubsub_topic.strip(),
            watch_attempted=True,
            watch_error=None,
        )
        connection.last_error = None
        _restore_connected(session, connection.id)
        logger.info("Registered Gmail watch business=%s", business_id)
        return connection
    except ProviderError as exc:
        message = str(exc) if str(exc) in {_RECONNECT, _WATCH_FAILURE, _NOT_CONFIGURED} else _WATCH_FAILURE
        _remember_watch_failure(session, connection, message)
        raise ProviderError(message) from None


def renew_expiring_gmail_watches(session: Session, *, now: datetime | None = None) -> int:
    """Renew watches that are inside the configured window of their Google expiration.

    Call this from a daily scheduler. There is no in-process worker.
    """
    settings = get_settings()
    if not settings.gmail_pubsub_configured():
        return 0
    moment = now or datetime.now(timezone.utc)
    window = timedelta(hours=max(settings.gmail_watch_renew_within_hours, 0))
    rows = session.scalars(
        select(ChannelConnection).where(
            ChannelConnection.provider == IntegrationProvider.GMAIL.value,
            ChannelConnection.status == ConnectionStatus.CONNECTED.value,
        )
    ).all()
    renewed = 0
    for connection in rows:
        expiration = _parse_time(_metadata(connection).get("watch_expiration"))
        if expiration is None or expiration - moment > window:
            continue
        try:
            _renew_one(session, connection, settings)
            renewed += 1
        except ProviderError:
            _remember_watch_failure(session, connection, _RENEW_FAILURE)
    return renewed


def receive_gmail_notification(session: Session, body: bytes) -> dict[str, int]:
    email, history_id = parse_pubsub_notification(body)
    connection = find_connected_account(session, IntegrationProvider.GMAIL, email)
    if connection is None:
        logger.info("Ignored Gmail notification for an unknown mailbox")
        return {"stored": 0}
    try:
        stored = _process_notification(session, connection, history_id)
    except ProviderError:
        _note_error(session, connection, _SYNC_FAILURE)
        raise ProviderError(_SYNC_FAILURE) from None
    _touch_notification(session, connection)
    return {"stored": stored}


def parse_pubsub_notification(body: bytes) -> tuple[str, str]:
    if len(body) > 1_000_000:
        raise ProviderError(_INVALID)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderError(_INVALID) from exc
    if not isinstance(payload, dict):
        raise ProviderError(_INVALID)
    if not _subscription_matches(payload.get("subscription")):
        raise ProviderError(_INVALID)
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ProviderError(_INVALID)
    data = message.get("data")
    if not isinstance(data, str) or not data.strip():
        raise ProviderError(_INVALID)
    try:
        padded = data.strip() + "=" * (-len(data.strip()) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode())
        note = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ProviderError(_INVALID) from exc
    if not isinstance(note, dict):
        raise ProviderError(_INVALID)
    email = str(note.get("emailAddress") or "").strip().lower()
    history_id = str(note.get("historyId") or "").strip()
    if not email or "@" not in email or not history_id:
        raise ProviderError(_INVALID)
    return email, history_id


def apply_gmail_history(
    session: Session,
    connection: ChannelConnection,
    start_history_id: str,
    *,
    notification_history_id: str | None = None,
) -> int:
    token = access_token_for(session, connection)
    try:
        message_ids, latest = _history_changes(token, start_history_id)
    except HistoryUnavailable:
        return _recover_history(session, connection, notification_history_id or start_history_id)
    stored = 0
    for message_id in message_ids:
        resource = gmail_get(message_url(message_id), token)
        if _store_gmail_resource(session, connection.business_id, resource):
            stored += 1
    target = _later_history(latest, notification_history_id or latest)
    _write_metadata(session, connection, history_id=target)
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_error = None
    session.commit()
    logger.info("Processed Gmail history business=%s stored=%s", connection.business_id, stored)
    return stored


def _watch_needs_recovery(row: ChannelConnection) -> bool:
    meta = _metadata(row)
    if meta.get("watch_enabled") is True or meta.get("watch_attempted") is True:
        return True
    watch_error = meta.get("watch_error")
    if isinstance(watch_error, str) and watch_error.strip():
        return True
    return _parse_time(meta.get("watch_expiration")) is not None


def gmail_realtime_fields(row: ChannelConnection | None, settings: Settings) -> dict:
    fields = {
        "listening": False,
        "realtime": "not_configured",
        "last_notification_at": None,
        "last_error": None if row is None else row.last_error,
        "pubsub_configured": settings.gmail_pubsub_configured(),
    }
    if row is None or row.status != ConnectionStatus.CONNECTED.value:
        if row is not None and row.status == ConnectionStatus.ERROR.value and _watch_needs_recovery(row):
            fields["realtime"] = "needs_attention"
        return fields
    meta = _metadata(row)
    expiration = _parse_time(meta.get("watch_expiration"))
    fields["last_notification_at"] = _parse_time(meta.get("last_notification_at"))
    now = datetime.now(timezone.utc)
    listening = meta.get("watch_enabled") is True and expiration is not None and expiration > now
    watch_error = meta.get("watch_error") if isinstance(meta.get("watch_error"), str) and meta.get("watch_error") else None
    if listening:
        fields["listening"] = True
        fields["realtime"] = "listening"
        return fields
    expired = expiration is not None and expiration <= now
    if watch_error or expired or meta.get("watch_attempted") is True:
        fields["realtime"] = "needs_attention"
        if watch_error:
            fields["last_error"] = watch_error
        return fields
    fields["realtime"] = "manual"
    return fields


def _process_notification(session: Session, connection: ChannelConnection, history_id: str) -> int:
    start = str(_metadata(connection).get("history_id") or "").strip()
    if not start:
        token = access_token_for(session, connection)
        stored = import_recent_messages(session, connection, token)
        _write_metadata(session, connection, history_id=history_id)
        connection.last_sync_at = datetime.now(timezone.utc)
        connection.last_error = None
        session.commit()
        return stored
    return apply_gmail_history(session, connection, start, notification_history_id=history_id)


def _recover_history(session: Session, connection: ChannelConnection, history_id: str) -> int:
    logger.info("Gmail history expired business=%s", connection.business_id)
    token = access_token_for(session, connection)
    stored = import_recent_messages(session, connection, token)
    profile = gmail_get(_PROFILE_URL, token)
    current = str(profile.get("historyId") or history_id).strip() or history_id
    _write_metadata(session, connection, history_id=_later_history(current, history_id))
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_error = None
    session.commit()
    return stored


def _renew_one(session: Session, connection: ChannelConnection, settings: Settings) -> None:
    token = access_token_for(session, connection)
    watched = gmail_post(
        _WATCH_URL,
        token,
        {"topicName": settings.gmail_pubsub_topic.strip(), "labelIds": ["INBOX"]},
    )
    expiration = _millis(watched.get("expiration"))
    if expiration is None:
        raise ProviderError(_RENEW_FAILURE)
    current = str(_metadata(connection).get("history_id") or "").strip()
    watched_history = str(watched.get("historyId") or current).strip()
    _write_metadata(
        session,
        connection,
        history_id=_later_history(current, watched_history) if current else watched_history,
        watch_enabled=True,
        watch_expiration=expiration.isoformat(),
        pubsub_topic=settings.gmail_pubsub_topic.strip(),
        watch_attempted=True,
        watch_error=None,
    )
    logger.info("Renewed Gmail watch business=%s", connection.business_id)


def _history_changes(access_token: str, start_history_id: str) -> tuple[list[str], str]:
    added: list[str] = []
    deleted: set[str] = set()
    latest = start_history_id
    page: str | None = None
    for _ in range(_MAX_HISTORY_PAGES):
        payload = gmail_get(_history_url(start_history_id, page), access_token)
        latest = _later_history(latest, str(payload.get("historyId") or latest))
        page_added, page_deleted = _changed_ids(payload.get("history"))
        deleted.update(page_deleted)
        for message_id in page_added:
            if message_id not in deleted and message_id not in added:
                added.append(message_id)
        token = payload.get("nextPageToken")
        if not isinstance(token, str) or not token:
            return [message_id for message_id in added if message_id not in deleted], latest
        page = token
    raise ProviderError(_SYNC_FAILURE)


def _history_url(start_history_id: str, page_token: str | None) -> str:
    pairs = [
        ("startHistoryId", start_history_id),
        ("historyTypes", "messageAdded"),
        ("historyTypes", "messageDeleted"),
    ]
    if page_token:
        pairs.append(("pageToken", page_token))
    return f"{_HISTORY_URL}?{urlencode(pairs)}"


def _changed_ids(history: object) -> tuple[list[str], list[str]]:
    added: list[str] = []
    deleted: list[str] = []
    if not isinstance(history, list):
        return added, deleted
    for record in history:
        if not isinstance(record, dict):
            continue
        for item in record.get("messagesDeleted") or []:
            message_id = _message_id(item)
            if message_id:
                deleted.append(message_id)
        for item in record.get("messagesAdded") or []:
            message_id = _message_id(item)
            if message_id:
                added.append(message_id)
    return added, deleted


def _message_id(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    message = item.get("message")
    if not isinstance(message, dict):
        return None
    message_id = str(message.get("id") or "").strip()
    return message_id or None


def _subscription_matches(subscription: object) -> bool:
    topic_project = _project(get_settings().gmail_pubsub_topic)
    subscription_project = _project(subscription if isinstance(subscription, str) else "")
    return bool(topic_project and topic_project == subscription_project)


def _project(resource: str) -> str | None:
    parts = resource.strip().split("/")
    if len(parts) >= 2 and parts[0] == "projects" and parts[1]:
        return parts[1]
    return None


def _remember_watch_failure(session: Session, connection: ChannelConnection, message: str) -> None:
    current = session.get(ChannelConnection, connection.id) or connection
    _restore_connected(session, current.id)
    current = session.get(ChannelConnection, connection.id) or current
    _write_metadata(session, current, watch_enabled=False, watch_attempted=True, watch_error=message)
    current.last_error = message
    session.commit()


def _note_error(session: Session, connection: ChannelConnection, message: str) -> None:
    current = session.get(ChannelConnection, connection.id)
    if current is None:
        return
    current.last_error = message
    if current.status == ConnectionStatus.CONNECTED.value:
        session.commit()
        return
    _restore_connected(session, current.id)


def _touch_notification(session: Session, connection: ChannelConnection) -> None:
    current = session.get(ChannelConnection, connection.id)
    if current is None:
        return
    _write_metadata(session, current, last_notification_at=datetime.now(timezone.utc).isoformat())


def _restore_connected(session: Session, connection_id: uuid.UUID) -> None:
    row = session.get(ChannelConnection, connection_id)
    if row is None:
        return
    if row.status != ConnectionStatus.CONNECTED.value:
        row.status = ConnectionStatus.CONNECTED.value
    session.commit()


def _write_metadata(session: Session, connection: ChannelConnection, **fields: object) -> None:
    current = dict(_metadata(connection))
    for key, value in fields.items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    connection.connection_metadata = current
    session.commit()


def _metadata(connection: ChannelConnection) -> dict:
    raw = connection.connection_metadata
    return dict(raw) if isinstance(raw, dict) else {}


def _later_history(current: str | None, candidate: str | None) -> str:
    if not candidate:
        return current or ""
    if not current:
        return candidate
    try:
        return candidate if int(candidate) > int(current) else current
    except ValueError:
        return candidate


def _millis(value: object) -> datetime | None:
    try:
        millis = int(str(value))
    except (TypeError, ValueError):
        return None
    if millis <= 0:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
