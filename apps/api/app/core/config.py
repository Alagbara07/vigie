from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    return Path.cwd()


def _env_file() -> Path | None:
    candidate = find_repo_root() / ".env"
    return candidate if candidate.is_file() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://vigie:vigie@localhost:5433/vigie"
    database_connect_timeout_seconds: int = 3
    database_pool_size: int = 5
    database_max_overflow: int = 5
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    port: int = 0
    app_env: str = "development"
    vigie_demo_mode: bool = False
    cors_origins: str = ""
    ai_provider: str = "heuristic"
    unanswered_request_threshold_minutes: int = 60
    nvidia_api_key: str = ""
    nvidia_model: str = ""
    nvidia_base_url: str = ""
    nvidia_timeout_seconds: float = 30
    public_web_url: str = "http://localhost:3000"
    api_public_url: str = ""
    oauth_state_ttl_seconds: int = 600
    session_ttl_seconds: int = 14 * 24 * 60 * 60
    credential_encryption_key: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_verify_token: str = ""
    meta_access_token: str = ""
    meta_whatsapp_business_account_id: str = ""
    meta_phone_number_id: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    gmail_pubsub_topic: str = ""
    gmail_pubsub_audience: str = ""
    gmail_pubsub_service_account: str = ""
    gmail_watch_renew_within_hours: int = 24
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = "common"
    microsoft_redirect_uri: str = ""

    def whatsapp_configured(self) -> bool:
        return bool(self.meta_app_secret.strip() and self.meta_verify_token.strip() and self.meta_access_token.strip())

    def resolved_google_redirect_uri(self) -> str:
        return self._explicit_or_public_api(self.google_redirect_uri, "/api/integrations/gmail/callback")

    def resolved_microsoft_redirect_uri(self) -> str:
        return self._explicit_or_public_api(self.microsoft_redirect_uri, "/api/integrations/microsoft/callback")

    def resolved_gmail_pubsub_audience(self) -> str:
        return self._explicit_or_public_api(self.gmail_pubsub_audience, "/api/integrations/gmail/pubsub")

    def whatsapp_webhook_url(self) -> str:
        return self._explicit_or_public_api("", "/api/integrations/whatsapp/webhook")

    def gmail_configured(self) -> bool:
        redirect = self.resolved_google_redirect_uri()
        if self.app_env == "production" and redirect and not redirect.startswith("https://"):
            return False
        return bool(self.google_client_id.strip() and self.google_client_secret.strip() and redirect)

    def gmail_pubsub_configured(self) -> bool:
        audience = self.resolved_gmail_pubsub_audience()
        if self.app_env == "production" and audience and not audience.startswith("https://"):
            return False
        return bool(self.gmail_pubsub_topic.strip() and audience and self.gmail_pubsub_service_account.strip())

    @model_validator(mode="after")
    def prepare_database_url(self) -> "Settings":
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        if self.app_env == "production" and "sslmode=" not in url:
            url = f"{url}{'&' if '?' in url else '?'}sslmode=require"
        self.database_url = url
        return self

    def listen_port(self) -> int:
        return self.port if self.port > 0 else self.api_port

    def allowed_web_origins(self) -> list[str]:
        origins: list[str] = []

        def add(value: str) -> None:
            cleaned = value.strip().rstrip("/")
            if cleaned and cleaned != "*" and cleaned not in origins:
                origins.append(cleaned)

        add(self.public_web_url)
        for item in self.cors_origins.split(","):
            add(item)
        if self.app_env != "production":
            add("http://localhost:3000")
            add("http://127.0.0.1:3000")
        return origins

    def production_configuration_error(self) -> str | None:
        if self.app_env != "production":
            return None
        web = self.public_web_url.strip()
        if not web.startswith("https://") or _is_local_origin(web):
            return "PUBLIC_WEB_URL must be the HTTPS origin of the deployed frontend."
        for origin in self.allowed_web_origins():
            if not origin.startswith("https://") or _is_local_origin(origin):
                return "Production browser origins must be exact HTTPS origins."
        return None

    def cookies_are_secure(self) -> bool:
        return self.app_env == "production" or self.public_web_url.startswith("https://")

    def microsoft_configured(self) -> bool:
        redirect = self.resolved_microsoft_redirect_uri()
        if self.app_env == "production" and redirect and not redirect.startswith("https://"):
            return False
        return bool(
            self.microsoft_client_id.strip()
            and self.microsoft_client_secret.strip()
            and self.microsoft_tenant_id.strip()
            and redirect
        )

    def _explicit_or_public_api(self, explicit: str, path: str) -> str:
        cleaned = explicit.strip()
        if cleaned:
            return cleaned
        base = self.api_public_url.strip().rstrip("/")
        if not base:
            return ""
        return f"{base}{path}"


def _is_local_origin(value: str) -> bool:
    host = value.split("://", 1)[-1].split("/", 1)[0].split("@")[-1].split(":", 1)[0].lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
