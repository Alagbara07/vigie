import base64
import json
import logging
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.enums import IntegrationProvider
from app.domain.errors import ProviderError
from app.integrations.connections import save_connection, store_credential
from app.integrations.gmail import HistoryUnavailable
from app.integrations.gmail_push import renew_expiring_gmail_watches
from app.models import Business, BusinessEvent, ChannelConnection, Commitment, IntegrationCredential, Message, Signal

LAGOS = ZoneInfo("Africa/Lagos")
WHEN = datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS)
PROMISE = "I'll pay the remaining ₦150,000 on Friday."
CLAIM = "I sent the ₦150,000 yesterday."
GREETING = "Good morning."
TOKEN = "gmail-access-token"
REFRESH = "gmail-refresh-token"
NEW_TOKEN = "gmail-refreshed-access-token"
EMAIL = "amaka@example.com"
OTHER_EMAIL = "other@example.com"
TOPIC = "projects/vigie-test/topics/gmail"
SUBSCRIPTION = "projects/vigie-test/subscriptions/gmail-push"
AUDIENCE = "https://api.example.com/api/integrations/gmail/pubsub"
SERVICE_ACCOUNT = "push@vigie-test.iam.gserviceaccount.com"


def test_watch_registration_stores_metadata_without_tokens(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "watch-shop")
    _connect(db_session, business, EMAIL)
    _patch_gmail(monkeypatch, _reading_get, _watch_post)
    with _pubsub_env():
        registered = api_client.post("/api/integrations/gmail/watch", params={"business_id": str(business.id)})
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
    assert registered.status_code == 200
    gmail = _gmail_status(listed.json())
    assert gmail["availability"] == "connected"
    assert gmail["listening"] is True
    assert gmail["realtime"] == "listening"
    assert gmail["pubsub_configured"] is True
    assert TOKEN not in listed.text
    assert REFRESH not in listed.text
    assert "google-secret" not in listed.text
    row = _connection(db_session, business.id)
    assert row.status == "connected"
    assert row.connection_metadata["watch_enabled"] is True
    assert row.connection_metadata["history_id"]
    assert row.connection_metadata["pubsub_topic"] == TOPIC
    assert row.connection_metadata["watch_expiration"]
    secret = db_session.get(IntegrationCredential, row.id)
    assert secret is not None
    assert secret.access_token.startswith("fernet:")
    assert TOKEN not in secret.access_token


def test_watch_failure_keeps_the_mailbox_connected(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "watch-fail")
    _connect(db_session, business, EMAIL)

    def explode(url: str, access_token: str, payload: dict) -> dict:
        del url, access_token, payload
        raise ProviderError("VIGIE could not sync Gmail.")

    _patch_gmail(monkeypatch, _reading_get, explode)
    with _pubsub_env():
        response = api_client.post("/api/integrations/gmail/watch", params={"business_id": str(business.id)})
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
    assert response.status_code == 503
    gmail = _gmail_status(listed.json())
    assert gmail["availability"] == "connected"
    assert gmail["listening"] is False
    assert gmail["realtime"] == "needs_attention"
    assert gmail["last_error"] == "Real-time listening could not be enabled."
    row = _connection(db_session, business.id)
    assert row.status == "connected"
    assert db_session.get(IntegrationCredential, row.id) is not None


def test_pubsub_notification_ingests_normalizes_and_isolates(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    business = _business(db_session, "push-shop")
    other = _business(db_session, "push-other")
    _connect(db_session, business, EMAIL, history_id="10")
    _connect(db_session, other, OTHER_EMAIL, history_id="10")
    _patch_gmail(monkeypatch, _reading_get)
    _allow_push(monkeypatch)
    with _pubsub_env(), caplog.at_level(logging.DEBUG):
        first = api_client.post("/api/integrations/gmail/pubsub", json=_push(EMAIL), headers={"Authorization": "Bearer push"})
        second = api_client.post("/api/integrations/gmail/pubsub", json=_push(EMAIL), headers={"Authorization": "Bearer push"})
        foreign = api_client.post(
            "/api/integrations/gmail/pubsub",
            json=_push("stranger@example.com"),
            headers={"Authorization": "Bearer push"},
        )
    assert first.status_code == 200
    assert first.json()["stored"] == 3
    assert second.status_code == 200
    assert second.json()["stored"] == 0
    assert foreign.json()["stored"] == 0
    assert _count(db_session, Message, business.id) == 3
    assert _count(db_session, Message, other.id) == 0
    events = list(db_session.scalars(select(BusinessEvent).where(BusinessEvent.business_id == business.id)))
    kinds = sorted(event.event_type for event in events)
    assert kinds == ["PAYMENT_CLAIM", "PAYMENT_COMMITMENT"]
    claim = next(event for event in events if event.event_type == "PAYMENT_CLAIM")
    assert claim.extracted_data["payment_verified"] is False
    commitment = db_session.scalar(select(Commitment).where(Commitment.business_id == business.id))
    assert commitment is not None and commitment.commitment_type == "PAYMENT_COMMITMENT"
    greeting = db_session.scalar(select(Message).where(Message.external_message_id == "g-hi"))
    assert greeting is not None and greeting.content == GREETING
    greeting_events = db_session.scalar(
        select(func.count()).select_from(BusinessEvent).where(BusinessEvent.source_message_id == greeting.id)
    )
    assert greeting_events == 0
    promise = db_session.scalar(select(Message).where(Message.external_message_id == "g-pay"))
    assert promise is not None
    assert promise.source == "gmail"
    assert promise.content == PROMISE
    assert promise.message_metadata["thread_id"] == "thread-g-pay"
    assert TOKEN not in caplog.text
    assert REFRESH not in caplog.text
    assert NEW_TOKEN not in caplog.text
    row = _connection(db_session, business.id)
    assert row.connection_metadata["history_id"] == "22"
    assert row.connection_metadata["last_notification_at"]


def test_duplicate_notification_does_not_duplicate_signals(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "push-twice")
    _connect(db_session, business, EMAIL, history_id="10")
    _patch_gmail(monkeypatch, _reading_get)
    _allow_push(monkeypatch)
    with _pubsub_env():
        api_client.post("/api/integrations/gmail/pubsub", json=_push(EMAIL), headers={"Authorization": "Bearer push"})
        signals = _count(db_session, Signal, business.id)
        events = _count(db_session, BusinessEvent, business.id)
        api_client.post("/api/integrations/gmail/pubsub", json=_push(EMAIL), headers={"Authorization": "Bearer push"})
    assert _count(db_session, Message, business.id) == 3
    assert _count(db_session, BusinessEvent, business.id) == events
    assert _count(db_session, Commitment, business.id) == 1
    assert _count(db_session, Signal, business.id) == signals


def test_expired_history_resyncs_recent_mail(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "history-gap")
    _connect(db_session, business, EMAIL, history_id="1")

    def gap(url: str, access_token: str) -> dict:
        assert access_token == TOKEN
        if "/history" in url:
            raise HistoryUnavailable("Gmail history is no longer available.")
        if "/profile" in url:
            return {"emailAddress": EMAIL, "historyId": "90"}
        if "messages?" in url:
            return {"messages": [{"id": "g-pay"}]}
        if "g-pay" in url:
            return _resource("g-pay", PROMISE)
        raise AssertionError(url)

    _patch_gmail(monkeypatch, gap)
    _allow_push(monkeypatch)
    with _pubsub_env():
        response = api_client.post("/api/integrations/gmail/pubsub", json=_push(EMAIL, "91"), headers={"Authorization": "Bearer push"})
    assert response.status_code == 200
    assert response.json()["stored"] == 1
    assert _connection(db_session, business.id).connection_metadata["history_id"] == "91"
    assert _count(db_session, Commitment, business.id) == 1


def test_pubsub_rejects_unsigned_unknown_and_invalid_payloads(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "push-guard")
    _connect(db_session, business, EMAIL, history_id="10")
    with _env(GMAIL_PUBSUB_TOPIC="", GMAIL_PUBSUB_AUDIENCE="", GMAIL_PUBSUB_SERVICE_ACCOUNT=""):
        unconfigured = api_client.post(
            "/api/integrations/gmail/pubsub",
            json=_push(EMAIL),
            headers={"Authorization": "Bearer anything"},
        )
    assert unconfigured.status_code == 403
    with _pubsub_env():
        missing = api_client.post("/api/integrations/gmail/pubsub", json=_push(EMAIL))
        invalid = api_client.post(
            "/api/integrations/gmail/pubsub",
            json={"message": {}},
            headers={"Authorization": "Bearer nope"},
        )
    assert missing.status_code == 401
    monkeypatch.setattr(
        "app.integrations.pubsub_auth.id_token.verify_oauth2_token",
        lambda token, request, audience=None: {"email": "other@bad.example", "email_verified": True},
    )
    with _pubsub_env():
        wrong_account = api_client.post(
            "/api/integrations/gmail/pubsub",
            json=_push(EMAIL),
            headers={"Authorization": "Bearer signed"},
        )
        _allow_push(monkeypatch)
        invalid_body = api_client.post(
            "/api/integrations/gmail/pubsub",
            json={"subscription": SUBSCRIPTION},
            headers={"Authorization": "Bearer signed"},
        )
        unknown = api_client.post(
            "/api/integrations/gmail/pubsub",
            json=_push("stranger@example.com"),
            headers={"Authorization": "Bearer signed"},
        )
    assert wrong_account.status_code == 401
    assert invalid.status_code == 401
    assert invalid_body.status_code == 400
    assert unknown.status_code == 200
    assert unknown.json()["stored"] == 0
    assert _count(db_session, Message, business.id) == 0


def test_token_refresh_replaces_the_stored_secret(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    business = _business(db_session, "refresh-shop")
    connection = _connect(db_session, business, EMAIL)
    secret = db_session.get(IntegrationCredential, connection.id)
    assert secret is not None
    secret.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    def refreshed(url: str, data: dict[str, str]) -> dict:
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == REFRESH
        assert "client_secret" in data
        return {"access_token": NEW_TOKEN, "expires_in": 3600}

    def fetch(url: str, access_token: str) -> dict:
        assert access_token == NEW_TOKEN
        if "messages?" in url:
            return {"messages": []}
        raise AssertionError(url)

    monkeypatch.setattr("app.integrations.gmail.post_form", refreshed)
    _patch_gmail(monkeypatch, fetch)
    with _pubsub_env(), caplog.at_level(logging.DEBUG):
        synced = api_client.post("/api/integrations/gmail/sync", params={"business_id": str(business.id)})
    assert synced.status_code == 200
    assert synced.json()["stored"] == 0
    db_session.refresh(secret)
    assert secret.access_token.startswith("fernet:")
    assert NEW_TOKEN not in secret.access_token
    assert REFRESH not in secret.access_token
    assert NEW_TOKEN not in caplog.text
    assert REFRESH not in caplog.text


def test_renewal_uses_google_expiration_and_keeps_history(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    soon = _business(db_session, "renew-soon")
    later = _business(db_session, "renew-later")
    soon_row = _connect(db_session, soon, "soon@example.com", history_id="80")
    later_row = _connect(db_session, later, "later@example.com", history_id="80")
    _stamp_watch(db_session, soon_row, datetime.now(timezone.utc) + timedelta(hours=1))
    _stamp_watch(db_session, later_row, datetime.now(timezone.utc) + timedelta(days=20))
    expiration_ms = int((datetime.now(timezone.utc) + timedelta(days=6)).timestamp() * 1000)

    def renew_post(url: str, access_token: str, payload: dict) -> dict:
        del url, payload
        assert access_token == TOKEN
        return {"historyId": "70", "expiration": str(expiration_ms)}

    _patch_gmail(monkeypatch, _reading_get, renew_post)
    with _pubsub_env():
        renewed = renew_expiring_gmail_watches(db_session)
    assert renewed == 1
    db_session.refresh(soon_row)
    db_session.refresh(later_row)
    assert soon_row.connection_metadata["history_id"] == "80"
    assert soon_row.connection_metadata["watch_enabled"] is True
    assert soon_row.connection_metadata["watch_expiration"] != later_row.connection_metadata["watch_expiration"]
    assert later_row.connection_metadata["history_id"] == "80"


def test_manual_status_when_pubsub_is_not_configured(api_client: TestClient, db_session: Session) -> None:
    business = _business(db_session, "manual-gmail")
    _connect(db_session, business, EMAIL)
    with _env(GMAIL_PUBSUB_TOPIC="", GMAIL_PUBSUB_AUDIENCE="", GMAIL_PUBSUB_SERVICE_ACCOUNT=""):
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
    gmail = _gmail_status(listed.json())
    assert gmail["availability"] == "connected"
    assert gmail["listening"] is False
    assert gmail["realtime"] == "manual"
    assert gmail["pubsub_configured"] is False


def _reading_get(url: str, access_token: str) -> dict:
    assert access_token == TOKEN
    if "/history" in url:
        return {
            "historyId": "22",
            "history": [
                {
                    "id": "20",
                    "messagesAdded": [
                        {"message": {"id": "g-pay", "threadId": "thread-g-pay"}},
                        {"message": {"id": "g-claim", "threadId": "thread-g-claim"}},
                        {"message": {"id": "g-hi", "threadId": "thread-g-hi"}},
                    ],
                },
                {"id": "21", "messagesDeleted": [{"message": {"id": "g-old"}}]},
            ],
        }
    if "/profile" in url:
        return {"emailAddress": EMAIL, "historyId": "15"}
    if "messages?" in url:
        return {"messages": []}
    if "g-pay" in url:
        return _resource("g-pay", PROMISE)
    if "g-claim" in url:
        return _resource("g-claim", CLAIM)
    if "g-hi" in url:
        return _resource("g-hi", GREETING)
    if "g-old" in url:
        raise AssertionError("deleted mail must not be fetched")
    raise AssertionError(url)


def _watch_post(url: str, access_token: str, payload: dict) -> dict:
    assert url.endswith("/watch")
    assert access_token == TOKEN
    assert payload["topicName"] == TOPIC
    expiration = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp() * 1000)
    return {"historyId": "22", "expiration": str(expiration)}


def _resource(message_id: str, text: str) -> dict:
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "internalDate": str(int(WHEN.timestamp() * 1000)),
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Amaka Bello <amaka@example.com>"},
                {"name": "To", "value": "shop@example.com"},
                {"name": "Subject", "value": "Balance"},
            ],
            "body": {"data": base64.urlsafe_b64encode(text.encode()).decode()},
        },
    }


def _push(email: str, history_id: str = "22") -> dict:
    data = base64.urlsafe_b64encode(
        json.dumps({"emailAddress": email, "historyId": history_id}).encode()
    ).decode()
    return {"message": {"data": data, "messageId": "push-1", "publishTime": "2026-09-27T12:00:00Z"}, "subscription": SUBSCRIPTION}


def _connect(session: Session, business: Business, email: str, history_id: str | None = None) -> ChannelConnection:
    row = save_connection(
        session,
        business_id=business.id,
        provider=IntegrationProvider.GMAIL,
        external_account_id=email,
        display_name=email,
        metadata={"scope": "https://www.googleapis.com/auth/gmail.readonly"},
    )
    store_credential(
        session,
        row,
        access_token=TOKEN,
        refresh_token=REFRESH,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    if history_id is not None:
        meta = dict(row.connection_metadata or {})
        meta["history_id"] = history_id
        row.connection_metadata = meta
        session.commit()
    return row


def _stamp_watch(session: Session, row: ChannelConnection, expiration: datetime) -> None:
    meta = dict(row.connection_metadata or {})
    meta.update(
        {
            "watch_enabled": True,
            "watch_expiration": expiration.isoformat(),
            "pubsub_topic": TOPIC,
            "history_id": meta.get("history_id") or "80",
        }
    )
    row.connection_metadata = meta
    session.commit()


def _patch_gmail(monkeypatch: pytest.MonkeyPatch, get, post=None) -> None:
    monkeypatch.setattr("app.integrations.gmail.gmail_get", get)
    monkeypatch.setattr("app.integrations.gmail_push.gmail_get", get)
    if post is not None:
        monkeypatch.setattr("app.integrations.gmail.gmail_post", post)
        monkeypatch.setattr("app.integrations.gmail_push.gmail_post", post)


def _allow_push(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.channels.verify_pubsub_push", lambda authorization, settings=None: None)


def _gmail_status(rows: list[dict]) -> dict:
    return next(row for row in rows if row["provider"] == "gmail")


def _connection(session: Session, business_id: uuid.UUID) -> ChannelConnection:
    row = session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.business_id == business_id,
            ChannelConnection.provider == "gmail",
        )
    )
    assert row is not None
    return row


def _count(session: Session, model: type, business_id: uuid.UUID) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id)) or 0)


def _business(session: Session, slug: str) -> Business:
    business = Business(name=slug, slug=slug, default_currency="NGN", timezone="Africa/Lagos")
    session.add(business)
    session.commit()
    return business


@contextmanager
def _pubsub_env() -> Iterator[None]:
    with _env(
        GOOGLE_CLIENT_ID="google-client",
        GOOGLE_CLIENT_SECRET="google-secret",
        GOOGLE_REDIRECT_URI="http://localhost:8000/api/integrations/gmail/callback",
        GMAIL_PUBSUB_TOPIC=TOPIC,
        GMAIL_PUBSUB_AUDIENCE=AUDIENCE,
        GMAIL_PUBSUB_SERVICE_ACCOUNT=SERVICE_ACCOUNT,
    ):
        yield


@contextmanager
def _env(**values: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        os.environ[key] = value
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        get_settings.cache_clear()
