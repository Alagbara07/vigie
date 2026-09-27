import hashlib
import hmac
import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.gmail import GmailAdapter
from app.integrations.microsoft import MicrosoftAdapter
from app.integrations.provider import OutboundDisabled
from app.models import Business, BusinessEvent, ChannelConnection, Commitment, IntegrationCredential, Message

LAGOS = ZoneInfo("Africa/Lagos")
WHEN = datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS)
PROMISE = "I'll pay the remaining ₦150,000 on Friday."
CLAIM = "I sent the ₦150,000 balance yesterday."
GREETING = "Good morning."
TOKEN = "gmail-access-token"
REFRESH = "gmail-refresh-token"
SECRET = "google-client-secret"


def test_channels_stay_unconfigured_without_provider_credentials(api_client: TestClient, db_session: Session) -> None:
    business = _business(db_session, "plain-shop")
    with _env(VIGIE_DEMO_MODE="true", META_APP_SECRET="", GOOGLE_CLIENT_ID="", MICROSOFT_CLIENT_ID=""):
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
    assert listed.status_code == 200
    by_provider = {item["provider"]: item for item in listed.json()}
    assert by_provider["whatsapp"]["availability"] == "not_configured"
    assert by_provider["gmail"]["availability"] == "not_configured"
    assert by_provider["microsoft365"]["availability"] == "not_configured"
    assert by_provider["demo"]["availability"] == "prototype"
    assert "access_token" not in listed.text
    assert api_client.get("/api/integrations", params={"business_id": str(uuid.uuid4())}).status_code == 404


def test_whatsapp_webhook_verifies_and_rejects_a_bad_signature(api_client: TestClient, db_session: Session) -> None:
    with _env(META_APP_SECRET="meta-secret", META_VERIFY_TOKEN="verify-token", META_ACCESS_TOKEN="meta-token"):
        verified = api_client.get(
            "/api/integrations/whatsapp/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "verify-token", "hub.challenge": "12345"},
        )
        rejected = api_client.get(
            "/api/integrations/whatsapp/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
        )
        unsigned = api_client.post(
            "/api/integrations/whatsapp/webhook",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
        signed = _post_whatsapp(api_client, {"unexpected": True}, "meta-secret")
        malformed = _post_whatsapp(api_client, None, "meta-secret", raw=b"not-json")
    assert verified.status_code == 200
    assert verified.text == "12345"
    assert rejected.status_code == 403
    assert unsigned.status_code == 403
    assert signed.status_code == 200
    assert signed.json() == {"received": 0, "stored": 0}
    assert malformed.status_code == 400
    assert "Traceback" not in malformed.text


def test_whatsapp_message_follows_the_existing_pipeline(api_client: TestClient, db_session: Session) -> None:
    shop = _business(db_session, "shop-a")
    other = _business(db_session, "shop-b")
    with _env(META_APP_SECRET="", META_VERIFY_TOKEN="", META_ACCESS_TOKEN=""):
        blocked = api_client.post(
            "/api/integrations/whatsapp/connect",
            json={"business_id": str(shop.id), "phone_number_id": "1001"},
        )
    assert blocked.status_code == 409
    with _env(META_APP_SECRET="meta-secret", META_VERIFY_TOKEN="verify-token", META_ACCESS_TOKEN="meta-token"):
        connected = api_client.post(
            "/api/integrations/whatsapp/connect",
            json={"business_id": str(shop.id), "phone_number_id": "1001", "display_name": "Adaeze line"},
        )
        conflict = api_client.post(
            "/api/integrations/whatsapp/connect",
            json={"business_id": str(other.id), "phone_number_id": "1001"},
        )
        other_line = api_client.post(
            "/api/integrations/whatsapp/connect",
            json={"business_id": str(other.id), "phone_number_id": "2002"},
        )
        payload = _whatsapp_payload("1001", "wamid.promise", PROMISE, "Amaka Bello")
        first = _post_whatsapp(api_client, payload, "meta-secret")
        second = _post_whatsapp(api_client, payload, "meta-secret")
        ignored = _post_whatsapp(api_client, _whatsapp_payload("9999", "wamid.other", PROMISE, "Ada"), "meta-secret")
        statuses = _post_whatsapp(api_client, {"entry": [{"changes": [{"value": {"statuses": [{"id": "1"}]}}]}]}, "meta-secret")
    assert connected.status_code == 200
    assert connected.json()["availability"] == "connected"
    assert connected.json()["account_label"] == "Adaeze line"
    assert "meta-token" not in connected.text
    assert conflict.status_code == 409
    assert other_line.status_code == 200
    assert first.json()["stored"] == 1
    assert second.json()["stored"] == 0
    assert ignored.json()["stored"] == 0
    assert statuses.status_code == 200
    messages = list(db_session.scalars(select(Message).where(Message.source == "whatsapp")))
    assert len(messages) == 1
    assert messages[0].business_id == shop.id
    assert messages[0].content == PROMISE
    assert messages[0].external_message_id == "wamid.promise"
    commitment = db_session.scalar(select(Commitment).where(Commitment.business_id == shop.id))
    assert commitment is not None
    assert commitment.commitment_type == "PAYMENT_COMMITMENT"
    assert commitment.status == "PENDING"
    assert commitment.amount == Decimal("150000.00")
    assert commitment.currency == "NGN"
    assert _count(db_session, BusinessEvent, shop.id) == 1
    assert _count(db_session, BusinessEvent, other.id) == 0
    assert _count(db_session, Message, other.id) == 0


def test_whatsapp_claim_is_not_verified_and_a_greeting_creates_nothing(
    api_client: TestClient,
    db_session: Session,
) -> None:
    business = _business(db_session, "claims")
    with _env(META_APP_SECRET="meta-secret", META_VERIFY_TOKEN="verify-token", META_ACCESS_TOKEN="meta-token"):
        api_client.post(
            "/api/integrations/whatsapp/connect",
            json={"business_id": str(business.id), "phone_number_id": "3003"},
        )
        claim = _post_whatsapp(api_client, _whatsapp_payload("3003", "wamid.claim", CLAIM, "Ngozi"), "meta-secret")
        greeting = _post_whatsapp(
            api_client,
            _whatsapp_payload("3003", "wamid.hello", GREETING, "Ngozi"),
            "meta-secret",
        )
    assert claim.status_code == 200
    assert greeting.status_code == 200
    events = list(db_session.scalars(select(BusinessEvent).where(BusinessEvent.business_id == business.id)))
    assert len(events) == 1
    assert events[0].event_type == "PAYMENT_CLAIM"
    assert events[0].extracted_data["payment_verified"] is False
    assert _count(db_session, Commitment, business.id) == 0
    greeting_message = db_session.scalar(select(Message).where(Message.external_message_id == "wamid.hello"))
    assert greeting_message is not None
    greeting_events = db_session.scalar(
        select(func.count()).select_from(BusinessEvent).where(BusinessEvent.source_message_id == greeting_message.id)
    )
    assert greeting_events == 0


def test_whatsapp_disconnect_stops_routing_and_hides_credentials(api_client: TestClient, db_session: Session) -> None:
    business = _business(db_session, "wa-off")
    with _env(
        META_APP_SECRET="meta-secret",
        META_VERIFY_TOKEN="verify-token",
        META_ACCESS_TOKEN="meta-token",
        API_PUBLIC_URL="https://vigie-api.example/",
    ):
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
        connected = api_client.post(
            "/api/integrations/whatsapp/connect",
            json={"business_id": str(business.id), "phone_number_id": "4040"},
        )
        disconnected = api_client.post(
            "/api/integrations/whatsapp/disconnect",
            json={"business_id": str(business.id)},
        )
        delivered = _post_whatsapp(api_client, _whatsapp_payload("4040", "wamid.after", PROMISE, "Ada"), "meta-secret")
    whatsapp = next(item for item in listed.json() if item["provider"] == "whatsapp")
    assert whatsapp["webhook_url"] == "https://vigie-api.example/api/integrations/whatsapp/webhook"
    assert whatsapp["availability"] == "available"
    assert "meta-token" not in listed.text
    assert "meta-secret" not in listed.text
    assert connected.status_code == 200
    assert disconnected.status_code == 200
    assert disconnected.json()["availability"] == "disconnected"
    assert delivered.json()["stored"] == 0
    row = db_session.scalar(select(ChannelConnection).where(ChannelConnection.business_id == business.id))
    assert row is not None
    assert row.external_account_id is None
    assert db_session.get(IntegrationCredential, row.id) is None
    assert _count(db_session, Message, business.id) == 0


def test_gmail_oauth_normalizes_and_isolates_the_business(api_client: TestClient, db_session: Session, monkeypatch) -> None:
    business = _business(db_session, "gmail-shop")
    other = _business(db_session, "gmail-other")
    monkeypatch.setattr("app.integrations.gmail.post_form", _gmail_token)
    monkeypatch.setattr("app.integrations.gmail.get_json", _gmail_get)
    monkeypatch.setattr("app.integrations.gmail.gmail_get", _gmail_get)
    with _env(
        GOOGLE_CLIENT_ID="google-client",
        GOOGLE_CLIENT_SECRET=SECRET,
        GOOGLE_REDIRECT_URI="http://localhost:8000/api/integrations/gmail/callback",
    ):
        missing = api_client.get("/api/integrations/gmail/connect", params={"business_id": str(uuid.uuid4())})
        started = api_client.get(
            "/api/integrations/gmail/connect",
            params={"business_id": str(business.id)},
            follow_redirects=False,
        )
        state = started.headers["location"].split("state=")[1].split("&")[0]
        callback = api_client.get(
            "/api/integrations/gmail/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        reused = api_client.get(
            "/api/integrations/gmail/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        invalid = api_client.get(
            "/api/integrations/gmail/callback",
            params={"code": "auth-code", "state": "missing-state"},
            follow_redirects=False,
        )
        synced = api_client.post("/api/integrations/gmail/sync", params={"business_id": str(business.id)})
        again = api_client.post("/api/integrations/gmail/sync", params={"business_id": str(business.id)})
        isolated = api_client.post("/api/integrations/gmail/sync", params={"business_id": str(other.id)})
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
    assert missing.status_code == 404
    assert "accounts.google.com" in started.headers["location"]
    assert SECRET not in started.headers["location"]
    assert callback.status_code == 302
    assert callback.headers["location"].endswith("/settings/integrations?connection=gmail")
    assert TOKEN not in callback.headers["location"]
    assert reused.status_code == 302
    assert "connection=error" in reused.headers["location"]
    assert "connection=error" in invalid.headers["location"]
    assert synced.status_code == 200
    assert synced.json()["stored"] == 1
    assert again.json()["stored"] == 0
    assert isolated.status_code == 404
    assert TOKEN not in listed.text
    assert REFRESH not in listed.text
    assert SECRET not in listed.text
    message = db_session.scalar(select(Message).where(Message.business_id == business.id))
    assert message is not None
    assert message.source == "gmail"
    assert message.content == PROMISE
    assert message.message_metadata["subject"] == "Balance"
    assert message.message_metadata["thread_id"] == "thread-1"
    commitment = db_session.scalar(select(Commitment).where(Commitment.business_id == business.id))
    assert commitment is not None and commitment.commitment_type == "PAYMENT_COMMITMENT"
    assert _count(db_session, Message, other.id) == 0
    direct = GmailAdapter().normalize_message(business.id, {"id": "", "payload": {}})
    assert direct is None


def test_microsoft_oauth_normalizes_and_rejects_a_bad_state(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    business = _business(db_session, "ms-shop")
    monkeypatch.setattr("app.integrations.microsoft.post_form", _microsoft_token)
    monkeypatch.setattr("app.integrations.microsoft.get_json", _microsoft_get)
    with _env(
        MICROSOFT_CLIENT_ID="ms-client",
        MICROSOFT_CLIENT_SECRET="ms-secret",
        MICROSOFT_TENANT_ID="common",
        MICROSOFT_REDIRECT_URI="http://localhost:8000/api/integrations/microsoft/callback",
    ):
        started = api_client.get(
            "/api/integrations/microsoft/connect",
            params={"business_id": str(business.id)},
            follow_redirects=False,
        )
        state = started.headers["location"].split("state=")[1].split("&")[0]
        bad = api_client.get(
            "/api/integrations/microsoft/callback",
            params={"code": "x", "state": "nope", "business_id": str(business.id)},
            follow_redirects=False,
        )
        callback = api_client.get(
            "/api/integrations/microsoft/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        synced = api_client.post("/api/integrations/microsoft/sync", params={"business_id": str(business.id)})
        listed = api_client.get("/api/integrations", params={"business_id": str(business.id)})
        disconnected = api_client.post(
            "/api/integrations/microsoft365/disconnect",
            json={"business_id": str(business.id)},
        )
    assert "login.microsoftonline.com" in started.headers["location"]
    assert "ms-secret" not in started.headers["location"]
    assert "connection=error" in bad.headers["location"]
    assert callback.headers["location"].endswith("/settings/integrations?connection=microsoft365")
    assert "ms-access-token" not in callback.headers["location"]
    assert synced.json()["stored"] == 1
    assert "ms-access-token" not in listed.text
    message = db_session.scalar(select(Message).where(Message.source == "microsoft365"))
    assert message is not None
    assert message.business_id == business.id
    assert message.content == PROMISE
    assert message.message_metadata["subject"] == "Balance"
    assert disconnected.json()["availability"] == "disconnected"
    secret = db_session.get(IntegrationCredential, _connection_id(db_session, business.id, "microsoft365"))
    assert secret is None
    assert "access_token" not in repr(IntegrationCredential(connection_id=uuid.uuid4(), access_token=TOKEN))
    blank = MicrosoftAdapter().normalize_message(business.id, {"id": "m-1"})
    assert blank is None


def test_approval_still_does_not_send() -> None:
    from app.integrations.whatsapp import WhatsAppAdapter

    with pytest.raises(OutboundDisabled):
        WhatsAppAdapter().send_message("2348000000000", "Hello")


def test_gmail_connect_is_unavailable_until_configured(api_client: TestClient, db_session: Session) -> None:
    business = _business(db_session, "no-google")
    with _env(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="", GOOGLE_REDIRECT_URI=""):
        response = api_client.get("/api/integrations/gmail/connect", params={"business_id": str(business.id)})
    assert response.status_code == 409
    assert response.json()["detail"] == "Configuration required."


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


def _business(session: Session, slug: str) -> Business:
    business = Business(name=slug, slug=slug, default_currency="NGN", timezone="Africa/Lagos")
    session.add(business)
    session.commit()
    return business


def _count(session: Session, model: type, business_id: uuid.UUID) -> int:
    return int(
        session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id)) or 0
    )


def _connection_id(session: Session, business_id: uuid.UUID, provider: str) -> uuid.UUID:
    row = session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.business_id == business_id,
            ChannelConnection.provider == provider,
        )
    )
    assert row is not None
    return row.id


def _post_whatsapp(client: TestClient, payload: dict | None, secret: str, raw: bytes | None = None):
    body = raw if raw is not None else json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/integrations/whatsapp/webhook",
        content=body,
        headers={"content-type": "application/json", "x-hub-signature-256": signature},
    )


def _whatsapp_payload(phone_number_id: str, external_id: str, text: str, name: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "contacts": [{"wa_id": "2348012345678", "profile": {"name": name}}],
                            "messages": [
                                {
                                    "from": "2348012345678",
                                    "id": external_id,
                                    "timestamp": str(int(WHEN.timestamp())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def _gmail_token(url: str, data: dict[str, str]) -> dict:
    assert data["client_secret"] == SECRET
    return {"access_token": TOKEN, "refresh_token": REFRESH, "expires_in": 3600}


def _gmail_get(url: str, access_token: str) -> dict:
    assert access_token == TOKEN
    if url.endswith("/profile"):
        return {"emailAddress": "amaka@example.com"}
    if "messages?" in url:
        return {"messages": [{"id": "g-1"}]}
    return {
        "id": "g-1",
        "threadId": "thread-1",
        "internalDate": str(int(WHEN.timestamp() * 1000)),
        "payload": {
            "headers": [
                {"name": "From", "value": "Amaka Bello <amaka@example.com>"},
                {"name": "To", "value": "adaeze@example.com"},
                {"name": "Subject", "value": "Balance"},
            ],
            "mimeType": "text/plain",
            "body": {"data": _b64(PROMISE)},
        },
    }


def _microsoft_token(url: str, data: dict[str, str]) -> dict:
    assert "ms-secret" == data["client_secret"]
    assert "common" in url
    return {"access_token": "ms-access-token", "refresh_token": "ms-refresh-token", "expires_in": 3600}


def _microsoft_get(url: str, access_token: str) -> dict:
    assert access_token == "ms-access-token"
    if url.startswith("https://graph.microsoft.com/v1.0/me?"):
        return {"id": "ms-user-1", "displayName": "Amaka Bello", "mail": "amaka@example.com"}
    return {
        "value": [
            {
                "id": "m-1",
                "conversationId": "conversation-1",
                "subject": "Balance",
                "receivedDateTime": WHEN.isoformat(),
                "from": {"emailAddress": {"name": "Amaka Bello", "address": "amaka@example.com"}},
                "toRecipients": [{"emailAddress": {"address": "adaeze@example.com"}}],
                "body": {"contentType": "text", "content": PROMISE},
            }
        ]
    }


def _b64(value: str) -> str:
    import base64

    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")

