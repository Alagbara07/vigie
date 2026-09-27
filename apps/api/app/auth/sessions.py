import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.cookies import SESSION_COOKIE
from app.core.config import get_settings
from app.models import User, UserSession


def issue_session(session: Session, user_id: uuid.UUID) -> str:
    raw = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            user_id=user_id,
            token_hash=_digest(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=get_settings().session_ttl_seconds),
        )
    )
    session.commit()
    return raw


def revoke_session(session: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    row = session.scalar(select(UserSession).where(UserSession.token_hash == _digest(raw_token)))
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = datetime.now(timezone.utc)
    session.commit()


def user_from_request_token(session: Session, raw_token: str | None) -> User | None:
    if not raw_token:
        return None
    row = session.scalar(select(UserSession).where(UserSession.token_hash == _digest(raw_token)))
    now = datetime.now(timezone.utc)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    return session.get(User, row.user_id)


def session_token(request_cookies: dict[str, str]) -> str | None:
    token = request_cookies.get(SESSION_COOKIE)
    return token or None


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
