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
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db, get_engine, get_sessionmaker

get_settings.cache_clear()
get_engine.cache_clear()
get_sessionmaker.cache_clear()

from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def engine() -> Engine:
    return get_engine()


@pytest.fixture()
def db_session():
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def api_client(db_session: Session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
