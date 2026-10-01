import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models import AuditEvent, IntegrationCredential, OAuthState

TOKEN = "gmail-access-token-should-stay-secret"
REFRESH = "gmail-refresh-token-should-stay-secret"


def test_signup_login_and_logout(strict_client: TestClient, db_session: Session) -> None:
    created = strict_client.post(
        "/api/auth/signup",
        json={"email": "Ada@Example.com", "name": "Ada", "password": "correct-horse"},
    )
    assert created.status_code == 201
    assert created.json()["user"]["email"] == "ada@example.com"
    assert "password" not in created.json()["user"]
    assert "password_hash" not in created.text
    assert strict_client.get("/api/auth/session").status_code == 200

    duplicate = strict_client.post(
        "/api/auth/signup",
        json={"email": "ada@example.com", "name": "Ada", "password": "correct-horse"},
    )
    assert duplicate.status_code == 409

    strict_client.post("/api/auth/logout")
    assert strict_client.get("/api/auth/session").status_code == 401
    assert strict_client.get("/api/signals", params={"business_id": str(uuid.uuid4())}).status_code == 401
    assert strict_client.get("/api/health").status_code == 200

    wrong = strict_client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-password"})
    missing = strict_client.post("/api/auth/login", json={"email": "missing@example.com", "password": "correct-horse"})
    assert wrong.status_code == 401
    assert missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]

    logged_in = strict_client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "correct-horse"},
    )
    assert logged_in.status_code == 200
    assert "password_hash" not in logged_in.text
    actions = list(db_session.scalars(select(AuditEvent).where(AuditEvent.action == "login")).all())
    assert actions
    assert all("correct-horse" not in str(item.event_metadata) for item in actions)


def test_business_membership_and_tenant_isolation(strict_client: TestClient) -> None:
    ada = strict_client
    ada.post("/api/auth/signup", json={"email": "ada@shop.test", "name": "Ada", "password": "correct-horse"})
    shop_a = ada.post("/api/businesses", json={"name": "Shop A", "slug": "shop-a"}).json()
    session = ada.get("/api/auth/session").json()
    assert session["current_business"]["id"] == shop_a["id"]
    assert session["current_business"]["role"] == "owner"
    shop_a_again = ada.post("/api/businesses", json={"name": "Shop A Two", "slug": "shop-a-two"}).json()
    switched = ada.post("/api/auth/current-business", json={"business_id": shop_a["id"]})
    assert switched.status_code == 200
    assert switched.json()["current_business"]["id"] == shop_a["id"]
    assert {item["id"] for item in switched.json()["businesses"]} == {shop_a["id"], shop_a_again["id"]}

    with TestClient(app) as bola:
        bola.post("/api/auth/signup", json={"email": "bola@shop.test", "name": "Bola", "password": "correct-horse"})
        shop_b = bola.post("/api/businesses", json={"name": "Shop B", "slug": "shop-b"}).json()
        assert ada.get("/api/signals", params={"business_id": shop_b["id"]}).status_code == 403
        assert ada.get(f"/api/businesses/{shop_b['id']}/customers").status_code == 403
        assert ada.get("/api/integrations", params={"business_id": shop_b["id"]}).status_code == 403
        assert (
            ada.post(
                f"/api/businesses/{shop_b['id']}/customers",
                json={"name": "Amaka", "contact_identifier": "2348011111111"},
            ).status_code
            == 403
        )
        assert (
            ada.post(
                f"/api/actions/{uuid.uuid4()}/approve",
                json={"business_id": shop_b["id"]},
            ).status_code
            == 403
        )
        assert bola.get("/api/signals", params={"business_id": shop_a["id"]}).status_code == 403
        foreign = bola.post("/api/auth/current-business", json={"business_id": shop_a["id"]})
        assert foreign.status_code == 403


def test_member_can_view_but_not_manage_integrations(strict_client: TestClient, db_session: Session) -> None:
    from app.auth.access import ensure_membership
    from app.domain.enums import MemberRole
    from app.models import User

    strict_client.post("/api/auth/signup", json={"email": "owner@shop.test", "name": "Owner", "password": "correct-horse"})
    shop = strict_client.post("/api/businesses", json={"name": "Owned", "slug": "owned-shop"}).json()
    with TestClient(app) as member_client:
        member_client.post(
            "/api/auth/signup",
            json={"email": "member@shop.test", "name": "Member", "password": "correct-horse"},
        )
        member = db_session.scalar(select(User).where(User.email == "member@shop.test"))
        assert member is not None
        ensure_membership(db_session, member.id, uuid.UUID(shop["id"]), MemberRole.MEMBER)
        assert member_client.get("/api/signals", params={"business_id": shop["id"]}).status_code == 200
        denied = member_client.get("/api/integrations/gmail/connect", params={"business_id": shop["id"]}, follow_redirects=False)
        assert denied.status_code == 403


def test_oauth_state_is_bound_to_user_business_and_provider(strict_client: TestClient, db_session: Session) -> None:
    strict_client.post("/api/auth/signup", json={"email": "ada@oauth.test", "name": "Ada", "password": "correct-horse"})
    shop = strict_client.post("/api/businesses", json={"name": "OAuth Shop", "slug": "oauth-shop"}).json()
    other = strict_client.post("/api/businesses", json={"name": "Other OAuth", "slug": "other-oauth"}).json()
    with _provider_env():
        started = strict_client.get(
            "/api/integrations/gmail/connect",
            params={"business_id": shop["id"]},
            follow_redirects=False,
        )
        stolen = strict_client.get(
            "/api/integrations/gmail/connect",
            params={"business_id": str(uuid.uuid4())},
            follow_redirects=False,
        )
    assert started.status_code == 302
    assert stolen.status_code == 404
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    row = db_session.scalar(select(OAuthState).where(OAuthState.state == state))
    assert row is not None
    assert str(row.business_id) == shop["id"]
    assert row.provider == "gmail"
    assert row.user_id is not None
    assert str(row.business_id) != other["id"]

    with TestClient(app) as other_user:
        other_user.post("/api/auth/signup", json={"email": "bola@oauth.test", "name": "Bola", "password": "correct-horse"})
        mismatched = other_user.get(
            "/api/integrations/gmail/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
    assert "connection=error" in mismatched.headers["location"]
    db_session.refresh(row)
    assert row.used_at is None

    wrong_provider = strict_client.get(
        "/api/integrations/microsoft/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert "connection=error" in wrong_provider.headers["location"]

    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db_session.commit()
    expired = strict_client.get(
        "/api/integrations/gmail/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert "connection=error" in expired.headers["location"]

    row.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    row.used_at = datetime.now(timezone.utc)
    db_session.commit()
    reused = strict_client.get(
        "/api/integrations/gmail/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert "connection=error" in reused.headers["location"]


def test_credentials_are_encrypted_and_not_logged(
    strict_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    strict_client.post("/api/auth/signup", json={"email": "ada@mail.test", "name": "Ada", "password": "correct-horse"})
    shop = strict_client.post("/api/businesses", json={"name": "Mail Shop", "slug": "mail-shop"}).json()
    monkeypatch.setattr("app.integrations.gmail.post_form", lambda url, data: {"access_token": TOKEN, "refresh_token": REFRESH, "expires_in": 3600})
    monkeypatch.setattr(
        "app.integrations.gmail.get_json",
        lambda url, access_token: {"emailAddress": "ada@gmail.com"} if "profile" in url else {"messages": []},
    )
    with _provider_env(), caplog.at_level(logging.DEBUG):
        started = strict_client.get("/api/integrations/gmail/connect", params={"business_id": shop["id"]}, follow_redirects=False)
        state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
        callback = strict_client.get(
            "/api/integrations/gmail/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        listed = strict_client.get("/api/integrations", params={"business_id": shop["id"]})
    assert callback.status_code == 302
    assert TOKEN not in callback.headers["location"]
    assert TOKEN not in listed.text
    assert REFRESH not in listed.text
    assert "client_secret" not in listed.text
    secret = db_session.scalar(select(IntegrationCredential))
    assert secret is not None
    assert secret.access_token is not None
    assert secret.access_token.startswith("fernet:")
    assert TOKEN not in secret.access_token
    assert secret.refresh_token is not None
    assert REFRESH not in secret.refresh_token
    assert TOKEN not in caplog.text
    assert REFRESH not in caplog.text
    connection = listed.json()
    assert all(item.get("account_label") != TOKEN for item in connection)

    disconnected = strict_client.post("/api/integrations/gmail/disconnect", json={"business_id": shop["id"]})
    assert disconnected.status_code == 200
    assert db_session.get(IntegrationCredential, secret.connection_id) is None
    actions = {item.action for item in db_session.scalars(select(AuditEvent)).all()}
    assert "integration_connected" in actions
    assert "integration_disconnected" in actions
    assert "business_created" in actions


def test_approval_records_the_member_and_an_audit_event(strict_client: TestClient, db_session: Session) -> None:
    strict_client.post("/api/auth/signup", json={"email": "ada@approve.test", "name": "Ada", "password": "correct-horse"})
    shop = strict_client.post("/api/businesses", json={"name": "Approve Shop", "slug": "approve-shop"}).json()
    customer = strict_client.post(
        f"/api/businesses/{shop['id']}/customers",
        json={"name": "Amaka Bello", "contact_identifier": "2348012345678"},
    ).json()
    conversation = strict_client.post(
        f"/api/businesses/{shop['id']}/conversations",
        json={"customer_id": customer["id"], "channel": "simulated"},
    ).json()
    message = strict_client.post(
        f"/api/businesses/{shop['id']}/conversations/{conversation['id']}/messages",
        json={
            "sender_type": "customer",
            "direction": "inbound",
            "content": "I'll pay the remaining ₦150,000 on Friday.",
            "occurred_at": "2026-09-22T10:00:00Z",
        },
    ).json()
    assert (
        strict_client.post(
            f"/api/messages/{message['id']}/analyze",
            json={"business_id": shop["id"], "reference_time": "2026-09-24T09:00:00+01:00"},
        ).status_code
        == 200
    )
    assert (
        strict_client.post(
            "/api/evaluations/run",
            json={"business_id": shop["id"], "reference_time": "2026-09-26T09:00:00+01:00"},
        ).status_code
        == 200
    )
    recommended = strict_client.post("/api/actions/recommend", json={"business_id": shop["id"]})
    assert recommended.status_code == 200
    action_id = recommended.json()["actions"][0]["id"]
    approved = strict_client.post(f"/api/actions/{action_id}/approve", json={"business_id": shop["id"]})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_by_user_id"] == strict_client.get("/api/auth/session").json()["user"]["id"]
    assert approved.json()["executed_at"] is None
    audit = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "recommendation_approved"))
    assert audit is not None
    assert audit.resource_id == action_id
    assert "150,000" not in str(audit.event_metadata)


def test_cross_site_post_is_rejected(strict_client: TestClient) -> None:
    strict_client.post("/api/auth/signup", json={"email": "ada@csrf.test", "name": "Ada", "password": "correct-horse"})
    blocked = strict_client.post(
        "/api/auth/logout",
        headers={"origin": "https://evil.example", "sec-fetch-site": "cross-site"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Cross-site request blocked."
    assert strict_client.get("/api/auth/session").status_code == 200


def test_production_origin_login_and_signup_stay_available(strict_client: TestClient) -> None:
    import os

    previous = {key: os.environ.get(key) for key in ("APP_ENV", "PUBLIC_WEB_URL", "CORS_ORIGINS")}
    os.environ["APP_ENV"] = "production"
    os.environ["PUBLIC_WEB_URL"] = "https://vigie-web.example"
    os.environ["CORS_ORIGINS"] = ""
    get_settings.cache_clear()
    try:
        created = strict_client.post(
            "/api/auth/signup",
            json={"email": "ada@origin.test", "name": "Ada", "password": "correct-horse"},
            headers={"origin": "https://vigie-web.example", "sec-fetch-site": "same-origin"},
        )
        assert created.status_code == 201
        session = {"cookie": f"vigie_session={created.cookies['vigie_session']}"}
        duplicate = strict_client.post(
            "/api/auth/signup",
            json={"email": "ada@origin.test", "name": "Ada", "password": "correct-horse"},
            headers={"origin": "https://vigie-web.example", "sec-fetch-site": "same-origin", **session},
        )
        assert duplicate.status_code == 409
        wrong = strict_client.post(
            "/api/auth/login",
            json={"email": "ada@origin.test", "password": "wrong-password"},
            headers={"origin": "https://Vigie-Web.example:443", "sec-fetch-site": "cross-site", **session},
        )
        assert wrong.status_code == 401
        logged_in = strict_client.post(
            "/api/auth/login",
            json={"email": "ada@origin.test", "password": "correct-horse"},
            headers={"origin": "https://vigie-web.example", "sec-fetch-site": "same-origin", **session},
        )
        assert logged_in.status_code == 200
        signed_in = {"cookie": f"vigie_session={logged_in.cookies['vigie_session']}"}
        deployment = strict_client.post(
            "/api/auth/logout",
            headers={
                "origin": "https://vigie-deploy.example",
                "sec-fetch-site": "same-origin",
                **signed_in,
            },
        )
        assert deployment.status_code == 204
        foreign = strict_client.post(
            "/api/auth/logout",
            headers={"origin": "https://evil.example", "sec-fetch-site": "cross-site", **signed_in},
        )
        assert foreign.status_code == 403
        assert strict_client.get("/api/signals", params={"business_id": str(uuid.uuid4())}).status_code == 401
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        get_settings.cache_clear()


def test_demo_entry_is_hidden_when_demo_mode_is_off(strict_client: TestClient) -> None:
    previous = get_settings()
    get_settings.cache_clear()
    from app.core.config import Settings

    # The helper below toggles the flag through the environment.
    import os

    old = os.environ.get("VIGIE_DEMO_MODE")
    os.environ["VIGIE_DEMO_MODE"] = "false"
    get_settings.cache_clear()
    try:
        assert strict_client.post("/api/auth/demo").status_code == 404
    finally:
        if old is None:
            os.environ.pop("VIGIE_DEMO_MODE", None)
        else:
            os.environ["VIGIE_DEMO_MODE"] = old
        get_settings.cache_clear()
    del previous
    del Settings


def _provider_env():
    import os
    from contextlib import contextmanager

    @contextmanager
    def _env():
        keys = {
            "GOOGLE_CLIENT_ID": "google-client",
            "GOOGLE_CLIENT_SECRET": "google-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:3000/api/integrations/gmail/callback",
            "MICROSOFT_CLIENT_ID": "ms-client",
            "MICROSOFT_CLIENT_SECRET": "ms-secret",
            "MICROSOFT_TENANT_ID": "common",
            "MICROSOFT_REDIRECT_URI": "http://localhost:3000/api/integrations/microsoft/callback",
        }
        previous = {key: os.environ.get(key) for key in keys}
        os.environ.update(keys)
        get_settings.cache_clear()
        try:
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            get_settings.cache_clear()

    return _env()
