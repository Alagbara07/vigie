import base64
import os
from pathlib import Path

from dotenv import dotenv_values

os.environ.setdefault(
    "CREDENTIAL_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(b"vigie-test-credential-key-32b!!!").decode(),
)
# Keep the suite off a developer machine's Pub/Sub project. Tests opt in.
os.environ["GMAIL_PUBSUB_TOPIC"] = ""
os.environ["GMAIL_PUBSUB_AUDIENCE"] = ""
os.environ["GMAIL_PUBSUB_SERVICE_ACCOUNT"] = ""

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
from fastapi import Depends, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.auth.deps import Principal, require_member, require_user, requested_business_id
from app.auth.passwords import hash_password
from app.core.config import get_settings
from app.core.database import get_db, get_engine, get_sessionmaker
from app.domain.enums import MemberRole
from app.models import Business, Membership, User

_TEST_OWNER_EMAIL = "test-owner@vigie.test"
_TEST_OWNER_HASH = hash_password("test-owner-password")

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


def _ensure_test_owner(session: Session) -> User:
    user = session.scalar(select(User).where(User.email == _TEST_OWNER_EMAIL))
    if user is None:
        user = User(email=_TEST_OWNER_EMAIL, name="Test Owner", password_hash=_TEST_OWNER_HASH)
        session.add(user)
        session.flush()
    for business in session.scalars(select(Business)).all():
        existing = session.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.business_id == business.id)
        )
        if existing is None:
            session.add(Membership(user_id=user.id, business_id=business.id, role=MemberRole.OWNER.value))
    session.flush()
    return user


async def _override_user(request: Request, session: Session = Depends(get_db)) -> Principal:
    del request
    return Principal(user=_ensure_test_owner(session), business_id=None, role=None)


async def _override_member(request: Request, session: Session = Depends(get_db)) -> Principal:
    user = _ensure_test_owner(session)
    business_id = await requested_business_id(request)
    role = None
    if business_id is not None:
        if session.get(Business, business_id) is None:
            raise HTTPException(status_code=404, detail="Business not found.")
        existing = session.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.business_id == business_id)
        )
        if existing is None:
            session.add(Membership(user_id=user.id, business_id=business_id, role=MemberRole.OWNER.value))
            session.flush()
        role = MemberRole.OWNER.value
    return Principal(user=user, business_id=business_id, role=role)


@pytest.fixture()
def api_client(db_session: Session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[require_member] = _override_member
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def strict_client(db_session: Session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
