from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    return Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_repo_root() / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://vigie:vigie@localhost:5433/vigie"
    database_connect_timeout_seconds: int = 3
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    app_env: str = "development"
    vigie_demo_mode: bool = False
    ai_provider: str = "heuristic"
    unanswered_request_threshold_minutes: int = 60
    nvidia_api_key: str = ""
    nvidia_model: str = ""
    nvidia_base_url: str = ""
    nvidia_timeout_seconds: float = 30
    public_web_url: str = "http://localhost:3000"
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

    def gmail_configured(self) -> bool:
        return bool(
            self.google_client_id.strip() and self.google_client_secret.strip() and self.google_redirect_uri.strip()
        )

    def gmail_pubsub_configured(self) -> bool:
        return bool(
            self.gmail_pubsub_topic.strip()
            and self.gmail_pubsub_audience.strip()
            and self.gmail_pubsub_service_account.strip()
        )

    def microsoft_configured(self) -> bool:
        return bool(
            self.microsoft_client_id.strip()
            and self.microsoft_client_secret.strip()
            and self.microsoft_tenant_id.strip()
            and self.microsoft_redirect_uri.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
