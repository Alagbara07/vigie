import uuid

from sqlalchemy.orm import Session

from app.models import AuditEvent

_BLOCKED = {
    "access_token",
    "refresh_token",
    "password",
    "password_hash",
    "client_secret",
    "authorization",
    "credential_encryption_key",
    "webhook_secret",
}


def record_audit(
    session: Session,
    *,
    user_id: uuid.UUID | None,
    business_id: uuid.UUID | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    safe = {key: value for key, value in (metadata or {}).items() if key not in _BLOCKED}
    event = AuditEvent(
        user_id=user_id,
        business_id=business_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        event_metadata=safe or None,
    )
    session.add(event)
    session.commit()
    return event
