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


@lru_cache
def get_settings() -> Settings:
    return Settings()
