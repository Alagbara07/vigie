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
from app.demo.clock import AFTER_DUE
from app.domain.enums import IntegrationProvider
from app.domain.errors import ProviderError
from app.integrations.connections import save_connection, store_credential
from app.integrations.microsoft_push import renew_expiring_microsoft_subscriptions
from app.models import Business, BusinessEvent, ChannelConnection, Commitment, IntegrationCredential, Message, Signal
from app.services.evaluation import run_evaluation

LAGOS = ZoneInfo("Africa/Lagos")
WHEN = datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS)
PROMISE = "I'll pay the remaining ₦150,000 on Friday."
TOKEN = "ms-access-token"
REFRESH = "ms-refresh-token"
EMAIL = "amaka@example.com"
SUBSCRIPTION = "sub-outlook-1"
FUTURE = "2027-01-01T00:00:00.0000000Z"


def test_connect_subscribes_and_a_notification_becomes_a_signal(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    business = _business(db_session, "ms-lifecycle")
    other = _business(db_session, "ms-lifecycle-other")
    captured: dict[str, str] = {}

    def tokens(url: str, data: dict[str, str], **kwargs: object) -> dict:
        del url, kwargs
        scope = data.get("scope", "")
        assert "Mail.Read" in scope
        assert "Mail.Send" not in scope
        return {"access_token": TOKEN, "refresh_token": REFRESH, "expires_in": 3600, "scope": scope}

    def profile(url: str, access_token: str, **kwargs: object) -> dict:
        del kwargs
        assert access_token == TOKEN
        assert url.startswith("https://graph.microsoft.com/v1.0/me?")
        return {"id": "ms-user-1", "displayName": "Amaka Bello", "mail": EMAIL}

    def graph(method: str, url: str, access_token: str, payload: dict | None, *, purpose: str) -> dict:
        assert access_token == TOKEN
        assert method == "POST"
        assert purpose == "microsoft_subscription"
        assert payload is not None
        assert payload["changeType"] == "created"
        assert payload["resource"] == "me/mailFolders('Inbox')/messages"
        assert payload["notificationUrl"].endswith("/api/integrations/microsoft/webhook")
        captured["state"] = payload["clientState"]
        return {"id": SUBSCRIPTION, "expirationDateTime": FUTURE}

    def message(url: str, access_token: str, **kwargs: object) -> dict:
        del kwargs
        assert access_token == TOKEN
        assert "m-pay" in url
        return _outlook(PROMISE)

    monkeypatch.setattr("app.integrations.microsoft.post_form", tokens)
    monkeypatch.setattr("app.integrations.microsoft.get_json", profile)
    monkeypatch.setattr("app.integrations.microsoft_push._graph", graph)
    monkeypatch.setattr("app.integrations.microsoft_push.get_json", message)
    with _env(), caplog.at_level(logging.DEBUG):
        started = api_client.get(
            "/api/integrations/microsoft/connect",
            params={"business_id": str(business.id)},
            follow_redirects=False,
        )
        state = started.headers["location"].split("state=")[1].split("&")[0]
        finished = api_client.get(
            "/api/integrations/microsoft/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
        note = {
            "value": [
                {
                    "subscriptionId": SUBSCRIPTION,
                    "clientState": captured["state"],
                    "changeType": "created",
                    "resource": "Users/someone/Messages/m-pay",
                    "resourceData": {"id": "m-pay"},
                    "businessId": str(other.id),
                }
            ]
        }
        first = api_client.post("/api/integrations/microsoft/webhook", json=note)
        second = api_client.post("/api/integrations/microsoft/webhook", json=note)
    assert finished.status_code == 302
    assert finished.headers["location"].endswith("connection=microsoft365")
    outlook = next(item for item in listed.json() if item["provider"] == "microsoft365")
    assert outlook["availability"] == "connected"
    assert outlook["account_label"] == EMAIL
    assert outlook["listening"] is True
    assert outlook["realtime"] == "listening"
    row = _connection(db_session, business.id)
    secret = db_session.get(IntegrationCredential, row.id)
    assert secret is not None and secret.access_token.startswith("fernet:")
    assert TOKEN not in secret.access_token
    assert REFRESH not in (secret.refresh_token or "")
    assert row.connection_metadata["subscription_id"] == SUBSCRIPTION
    assert row.connection_metadata["subscription_enabled"] is True
    assert captured["state"] not in str(row.connection_metadata)
    assert first.status_code == 202
    assert second.status_code == 202
    assert _count(db_session, Message, business.id) == 1
    assert _count(db_session, Message, other.id) == 0
    stored = db_session.scalar(select(Message).where(Message.business_id == business.id))
    assert stored is not None
    assert stored.source == "microsoft365"
    assert stored.content == PROMISE
    assert stored.external_message_id == "m-pay"
    assert _count(db_session, Commitment, business.id) == 1
    assert _count(db_session, BusinessEvent, business.id) == 1
    evaluated = run_evaluation(db_session, business.id, AFTER_DUE)
    assert evaluated.signals_created == 1
    signals = api_client.get("/api/signals", params={"business_id": str(business.id)})
    hidden = api_client.get("/api/signals", params={"business_id": str(other.id)})
    assert signals.status_code == 200
    assert len(signals.json()) == 1
    assert signals.json()[0]["signal_type"] == "OVERDUE_PAYMENT"
    assert hidden.json() == []
    assert TOKEN not in caplog.text
    assert captured["state"] not in caplog.text


def test_replacing_a_subscription_deletes_the_previous_one(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "ms-replace")
    _connect(db_session, business, client_state="old-state")
    methods: list[str] = []

    def graph(method: str, url: str, access_token: str, payload: dict | None, *, purpose: str) -> dict:
        del access_token
        methods.append(method)
        if method == "DELETE":
            assert url.endswith(f"/{SUBSCRIPTION}")
            assert purpose == "microsoft_subscription_delete"
            return {}
        assert payload is not None
        assert payload["clientState"] != "old-state"
        return {"id": "sub-outlook-2", "expirationDateTime": FUTURE}

    monkeypatch.setattr("app.integrations.microsoft_push._graph", graph)
    with _env():
        from app.integrations.microsoft_push import register_microsoft_subscription

        register_microsoft_subscription(db_session, business.id)
    assert methods == ["DELETE", "POST"]
    row = _connection(db_session, business.id)
    assert row.connection_metadata["subscription_id"] == "sub-outlook-2"
    assert row.connection_metadata["subscription_enabled"] is True


def test_webhook_handshake_rejects_invalid_notifications(api_client: TestClient) -> None:
    with _env():
        handshake = api_client.get(
            "/api/integrations/microsoft/webhook",
            params={"validationToken": "graph-validation"},
        )
        broken = api_client.get(
            "/api/integrations/microsoft/webhook",
            params={"validationToken": "bad\ntoken"},
        )
        missing = api_client.post("/api/integrations/microsoft/webhook", json={"value": "nope"})
        garbage = api_client.post(
            "/api/integrations/microsoft/webhook",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
    assert handshake.status_code == 200
    assert handshake.text == "graph-validation"
    assert handshake.headers["content-type"].startswith("text/plain")
    assert broken.status_code == 400
    assert missing.status_code == 400
    assert garbage.status_code == 400


def test_unknown_subscription_and_client_state_do_not_import(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "ms-guard")
    _connect(db_session, business, client_state="expected-state")
    monkeypatch.setattr(
        "app.integrations.microsoft_push.get_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("message must not be fetched")),
    )
    with _env():
        wrong_state = api_client.post(
            "/api/integrations/microsoft/webhook",
            json=_note(SUBSCRIPTION, "other-state"),
        )
        unknown = api_client.post(
            "/api/integrations/microsoft/webhook",
            json=_note("someone-elses-subscription", "expected-state"),
        )
        blank = api_client.post(
            "/api/integrations/microsoft/webhook",
            json={"value": [{"subscriptionId": SUBSCRIPTION, "clientState": "expected-state"}]},
        )
    assert wrong_state.status_code == 202
    assert unknown.status_code == 202
    assert blank.status_code == 202
    assert _count(db_session, Message, business.id) == 0


def test_renewal_skips_fresh_subscriptions_and_continues_after_one_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    soon_business = _business(db_session, "ms-renew-soon")
    later_business = _business(db_session, "ms-renew-later")
    broken_business = _business(db_session, "ms-renew-broken")
    soon = _connect(db_session, soon_business, client_state="soon", hours=2, email="soon@example.com")
    later = _connect(db_session, later_business, client_state="later", hours=72, email="later@example.com")
    broken = _connect(db_session, broken_business, client_state="broken", hours=1, email="broken@example.com")
    calls: list[str] = []

    def graph(method: str, url: str, access_token: str, payload: dict | None, *, purpose: str) -> dict:
        del access_token, payload
        assert method == "PATCH"
        assert purpose == "microsoft_subscription_renew"
        calls.append(url)
        if broken.connection_metadata["subscription_id"] in url:
            raise ProviderError("Real-time listening could not be renewed.")
        return {"expirationDateTime": FUTURE}

    monkeypatch.setattr("app.integrations.microsoft_push._graph", graph)
    with _env():
        renewed = renew_expiring_microsoft_subscriptions(db_session)
    assert renewed == 1
    db_session.refresh(soon)
    db_session.refresh(later)
    db_session.refresh(broken)
    assert soon.connection_metadata["subscription_expiration"].startswith("2027-01-01T00:00:00")
    assert soon.connection_metadata["subscription_enabled"] is True
    assert later.connection_metadata["subscription_expiration"] != FUTURE
    assert broken.connection_metadata["subscription_enabled"] is False
    assert broken.status == "connected"
    assert len(calls) == 2


def test_revoked_token_keeps_the_mailbox_and_stops_import(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "ms-revoked")
    row = _connect(db_session, business, client_state="revoked-state")
    secret = db_session.get(IntegrationCredential, row.id)
    assert secret is not None
    secret.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    def tokens(url: str, data: dict[str, str], **kwargs: object) -> dict:
        del url, data, kwargs
        raise ProviderError("Microsoft 365 needs to be reconnected.")

    monkeypatch.setattr("app.integrations.microsoft.post_form", tokens)
    with _env():
        delivered = api_client.post(
            "/api/integrations/microsoft/webhook",
            json=_note(row.connection_metadata["subscription_id"], "revoked-state"),
        )
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
    assert delivered.status_code == 202
    outlook = next(item for item in listed.json() if item["provider"] == "microsoft365")
    assert outlook["availability"] == "error"
    assert outlook["account_label"] == EMAIL
    assert _count(db_session, Message, business.id) == 0


def test_disconnect_deletes_the_subscription_and_blocks_later_mail(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "ms-off")
    row = _connect(db_session, business, client_state="stop-state")
    deleted: list[str] = []

    def graph(method: str, url: str, access_token: str, payload: dict | None, *, purpose: str) -> dict:
        del access_token, payload
        assert method == "DELETE"
        assert purpose == "microsoft_subscription_delete"
        deleted.append(url)
        return {}

    monkeypatch.setattr("app.integrations.microsoft_push._graph", graph)
    monkeypatch.setattr(
        "app.integrations.microsoft_push.get_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("disconnected mail must not be fetched")),
    )
    with _env():
        disconnected = api_client.post(
            "/api/integrations/microsoft365/disconnect",
            json={"business_id": str(business.id)},
        )
        delivered = api_client.post(
            "/api/integrations/microsoft/webhook",
            json=_note(SUBSCRIPTION, "stop-state"),
        )
    assert deleted and deleted[0].endswith(f"/{SUBSCRIPTION}")
    assert disconnected.status_code == 200
    assert disconnected.json()["availability"] == "disconnected"
    assert disconnected.json()["account_label"] is None
    assert delivered.status_code == 202
    assert _count(db_session, Message, business.id) == 0
    stored = db_session.get(ChannelConnection, row.id)
    assert stored is not None
    assert stored.connection_metadata == {}
    assert db_session.get(IntegrationCredential, row.id) is None


def test_https_is_required_before_a_subscription_is_created(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business = _business(db_session, "ms-manual")

    def explode(*args: object, **kwargs: object) -> dict:
        del args, kwargs
        raise AssertionError("subscription must not be created")

    monkeypatch.setattr("app.integrations.microsoft.post_form", lambda *args, **kwargs: {
        "access_token": TOKEN,
        "refresh_token": REFRESH,
        "expires_in": 3600,
        "scope": "openid email offline_access https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Read",
    })
    monkeypatch.setattr(
        "app.integrations.microsoft.get_json",
        lambda *args, **kwargs: {"id": "ms-user", "displayName": "Amaka", "mail": EMAIL},
    )
    monkeypatch.setattr("app.integrations.microsoft_push._graph", explode)
    with _env(API_PUBLIC_URL="http://vigie-api.example"):
        started = api_client.get(
            "/api/integrations/microsoft/connect",
            params={"business_id": str(business.id)},
            follow_redirects=False,
        )
        state = started.headers["location"].split("state=")[1].split("&")[0]
        api_client.get(
            "/api/integrations/microsoft/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
    outlook = next(item for item in listed.json() if item["provider"] == "microsoft365")
    assert outlook["availability"] == "connected"
    assert outlook["listening"] is False
    assert outlook["realtime"] == "manual"
    row = _connection(db_session, business.id)
    assert "subscription_id" not in (row.connection_metadata or {})


def test_signals_list_is_empty_until_evaluation_creates_one(api_client: TestClient, db_session: Session) -> None:
    business = _business(db_session, "no-signals")
    empty = api_client.get("/api/signals", params={"business_id": str(business.id)})
    assert empty.status_code == 200
    assert empty.json() == []
    assert _count(db_session, Signal, business.id) == 0


def _note(subscription_id: str, client_state: str) -> dict:
    return {
        "value": [
            {
                "subscriptionId": subscription_id,
                "clientState": client_state,
                "changeType": "created",
                "resourceData": {"id": "m-pay"},
            }
        ]
    }


def _outlook(text: str) -> dict:
    return {
        "id": "m-pay",
        "conversationId": "conversation-1",
        "subject": "Balance",
        "receivedDateTime": WHEN.isoformat(),
        "from": {"emailAddress": {"name": "Amaka Bello", "address": "amaka@example.com"}},
        "toRecipients": [{"emailAddress": {"address": "adaeze@example.com"}}],
        "body": {"contentType": "text", "content": text},
    }


def _connect(
    session: Session,
    business: Business,
    *,
    client_state: str,
    hours: int = 48,
    email: str = EMAIL,
) -> ChannelConnection:
    row = save_connection(
        session,
        business_id=business.id,
        provider=IntegrationProvider.MICROSOFT365,
        external_account_id=email,
        display_name=email,
        metadata={
            "mail": email,
            "subscription_id": SUBSCRIPTION if hours != 1 else "sub-broken",
            "subscription_expiration": (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(),
            "subscription_client_state_hash": __import__("hashlib").sha256(client_state.encode()).hexdigest(),
            "subscription_enabled": True,
        },
    )
    store_credential(
        session,
        row,
        access_token=TOKEN,
        refresh_token=REFRESH,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    return row


def _connection(session: Session, business_id: uuid.UUID) -> ChannelConnection:
    row = session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.business_id == business_id,
            ChannelConnection.provider == "microsoft365",
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
def _env(**values: str) -> Iterator[None]:
    defaults = {
        "MICROSOFT_CLIENT_ID": "ms-client",
        "MICROSOFT_CLIENT_SECRET": "ms-secret",
        "MICROSOFT_TENANT_ID": "common",
        "API_PUBLIC_URL": "https://vigie-api.example",
    }
    defaults.update(values)
    previous = {key: os.environ.get(key) for key in defaults}
    os.environ.update(defaults)
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
