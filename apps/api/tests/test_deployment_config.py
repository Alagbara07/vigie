import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.config import get_settings
from app.main import create_app

NEON_WITH_SSL = "postgresql://vigie:obvious-fake@ep-example.neon.tech/vigie?sslmode=require"
NEON_WITHOUT_SSL = "postgres://vigie:obvious-fake@ep-example.neon.tech/vigie"
LOCAL_URL = "postgresql+psycopg://vigie:vigie@localhost:5433/vigie"


@contextmanager
def _env(**values: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
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


def test_neon_url_uses_psycopg_and_keeps_ssl_in_production() -> None:
    with _env(
        APP_ENV="production",
        DATABASE_URL=NEON_WITH_SSL,
        PUBLIC_WEB_URL="https://vigie-web.example",
        CORS_ORIGINS="https://vigie-preview.example,https://vigie-web.example",
        VIGIE_DEMO_MODE="false",
    ):
        settings = get_settings()
        assert settings.database_url.startswith("postgresql+psycopg://")
        assert settings.database_url.count("sslmode=") == 1
        assert "sslmode=require" in settings.database_url
        assert settings.cookies_are_secure() is True
        assert settings.vigie_demo_mode is False
        assert settings.allowed_web_origins() == [
            "https://vigie-web.example",
            "https://vigie-preview.example",
        ]


def test_production_adds_ssl_and_secure_cookies_without_localhost_origins() -> None:
    with _env(
        APP_ENV="production",
        DATABASE_URL=NEON_WITHOUT_SSL,
        PUBLIC_WEB_URL="https://vigie-web.example",
        CORS_ORIGINS="https://vigie-preview.example",
        VIGIE_DEMO_MODE="false",
    ):
        settings = get_settings()
        assert settings.database_url.startswith("postgresql+psycopg://")
        assert "sslmode=require" in settings.database_url
        assert "localhost" not in settings.database_url
        origins = settings.allowed_web_origins()
        assert "http://localhost:3000" not in origins
        assert "http://127.0.0.1:3000" not in origins
        assert "*" not in origins
        application = create_app()
        assert application.docs_url is None
        assert application.redoc_url is None
        assert application.openapi_url is None


def test_local_url_stays_without_ssl_and_cookies_stay_unsecured() -> None:
    with _env(
        APP_ENV="development",
        DATABASE_URL=LOCAL_URL,
        PUBLIC_WEB_URL="http://localhost:3000",
        CORS_ORIGINS="",
        VIGIE_DEMO_MODE="true",
        PORT="0",
        API_PORT="8000",
    ):
        settings = get_settings()
        assert settings.database_url == LOCAL_URL
        assert "sslmode=" not in settings.database_url
        assert settings.cookies_are_secure() is False
        assert settings.vigie_demo_mode is True
        assert settings.listen_port() == 8000
        assert "http://localhost:3000" in settings.allowed_web_origins()
        assert "http://127.0.0.1:3000" in settings.allowed_web_origins()


def test_render_port_overrides_the_local_api_port() -> None:
    with _env(PORT="10000", API_PORT="8000"):
        assert get_settings().listen_port() == 10000


def test_production_callbacks_and_pubsub_require_https() -> None:
    with _env(
        APP_ENV="production",
        DATABASE_URL=NEON_WITH_SSL,
        GOOGLE_CLIENT_ID="client",
        GOOGLE_CLIENT_SECRET="secret",
        API_PUBLIC_URL="",
        GOOGLE_REDIRECT_URI="http://vigie-api.example/api/integrations/gmail/callback",
        GMAIL_PUBSUB_TOPIC="projects/vigie-test/topics/gmail",
        GMAIL_PUBSUB_AUDIENCE="http://vigie-api.example/api/integrations/gmail/pubsub",
        GMAIL_PUBSUB_SERVICE_ACCOUNT="pubsub-push@vigie-test.iam.gserviceaccount.com",
        MICROSOFT_CLIENT_ID="client",
        MICROSOFT_CLIENT_SECRET="secret",
        MICROSOFT_TENANT_ID="common",
        MICROSOFT_REDIRECT_URI="http://vigie-api.example/api/integrations/microsoft/callback",
    ):
        settings = get_settings()
        assert settings.gmail_configured() is False
        assert settings.gmail_pubsub_configured() is False
        assert settings.microsoft_configured() is False

    with _env(
        APP_ENV="production",
        DATABASE_URL=NEON_WITH_SSL,
        GOOGLE_CLIENT_ID="client",
        GOOGLE_CLIENT_SECRET="secret",
        API_PUBLIC_URL="https://ignored.example",
        GOOGLE_REDIRECT_URI="https://vigie-api.example/api/integrations/gmail/callback",
        GMAIL_PUBSUB_TOPIC="projects/vigie-test/topics/gmail",
        GMAIL_PUBSUB_AUDIENCE="https://vigie-api.example/api/integrations/gmail/pubsub",
        GMAIL_PUBSUB_SERVICE_ACCOUNT="pubsub-push@vigie-test.iam.gserviceaccount.com",
        MICROSOFT_CLIENT_ID="client",
        MICROSOFT_CLIENT_SECRET="secret",
        MICROSOFT_TENANT_ID="common",
        MICROSOFT_REDIRECT_URI="https://vigie-api.example/api/integrations/microsoft/callback",
    ):
        settings = get_settings()
        assert settings.gmail_configured() is True
        assert settings.gmail_pubsub_configured() is True
        assert settings.microsoft_configured() is True
        assert settings.resolved_google_redirect_uri() == "https://vigie-api.example/api/integrations/gmail/callback"


def test_public_api_url_derives_callbacks_webhooks_and_cors() -> None:
    with _env(
        APP_ENV="production",
        DATABASE_URL=NEON_WITH_SSL,
        PUBLIC_WEB_URL="https://vigie-web.example",
        CORS_ORIGINS="*",
        API_PUBLIC_URL="https://vigie-api.example/",
        GOOGLE_CLIENT_ID="client",
        GOOGLE_CLIENT_SECRET="secret",
        GOOGLE_REDIRECT_URI="",
        GMAIL_PUBSUB_TOPIC="projects/vigie-test/topics/gmail",
        GMAIL_PUBSUB_AUDIENCE="",
        GMAIL_PUBSUB_SERVICE_ACCOUNT="pubsub-push@vigie-test.iam.gserviceaccount.com",
        MICROSOFT_CLIENT_ID="client",
        MICROSOFT_CLIENT_SECRET="secret",
        MICROSOFT_TENANT_ID="common",
        MICROSOFT_REDIRECT_URI="",
    ):
        settings = get_settings()
        assert settings.resolved_google_redirect_uri() == "https://vigie-api.example/api/integrations/gmail/callback"
        assert settings.resolved_microsoft_redirect_uri() == "https://vigie-api.example/api/integrations/microsoft/callback"
        assert settings.resolved_gmail_pubsub_audience() == "https://vigie-api.example/api/integrations/gmail/pubsub"
        assert settings.whatsapp_webhook_url() == "https://vigie-api.example/api/integrations/whatsapp/webhook"
        assert settings.gmail_configured() is True
        assert settings.gmail_pubsub_configured() is True
        assert settings.microsoft_configured() is True
        assert settings.allowed_web_origins() == ["https://vigie-web.example"]
        assert settings.production_configuration_error() is None


def test_production_rejects_a_local_frontend_origin() -> None:
    with _env(
        APP_ENV="production",
        DATABASE_URL=NEON_WITH_SSL,
        PUBLIC_WEB_URL="http://localhost:3000",
        CORS_ORIGINS="",
        API_PUBLIC_URL="",
    ):
        assert get_settings().production_configuration_error() == (
            "PUBLIC_WEB_URL must be the HTTPS origin of the deployed frontend."
        )


def test_demo_mode_follows_the_environment() -> None:
    with _env(VIGIE_DEMO_MODE="false"):
        assert get_settings().vigie_demo_mode is False
    with _env(VIGIE_DEMO_MODE="true"):
        assert get_settings().vigie_demo_mode is True


def test_render_renews_gmail_watches_and_microsoft_subscriptions() -> None:
    root = Path(__file__).resolve().parents[3]
    blueprint = (root / "render.yaml").read_text(encoding="utf-8")
    assert "python -m app.jobs.renew_gmail_watches" in blueprint
    assert "python -m app.jobs.renew_microsoft_subscriptions" in blueprint
    assert "python -m app.jobs.evaluate_signals" in blueprint
    assert "vigie-microsoft-subscription-renewal" in blueprint
    assert "vigie-signal-evaluation" in blueprint
