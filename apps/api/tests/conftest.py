import os
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://vigie:vigie@localhost:5433/vigie_test"


def repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    return Path.cwd()


file_env = dotenv_values(repo_root() / ".env")
os.environ["DATABASE_URL"] = (
    os.environ.get("TEST_DATABASE_URL")
    or file_env.get("TEST_DATABASE_URL")
    or DEFAULT_TEST_DATABASE_URL
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.core.database import get_engine

get_settings.cache_clear()
get_engine.cache_clear()

from app.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def engine() -> Engine:
    return get_engine()
