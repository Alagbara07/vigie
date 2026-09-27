import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import role_for
from app.auth.crypto import open_secret, seal_secret
from app.core.config import Settings, get_settings
from app.domain.enums import ConnectionStatus, IntegrationProvider
from app.domain.errors import ConflictError, NotFoundError, ProviderError
from app.models import Business, ChannelConnection, IntegrationCredential, OAuthState

CATALOG = (
    {
        "provider": IntegrationProvider.WHATSAPP,
        "label": "WhatsApp Business",
        "description": "Monitor customer conversations and identify commitments, payment claims and requests.",
    },
    {
        "provider": IntegrationProvider.GMAIL,
        "label": "Google Workspace",
        "description": "Analyze business email conversations.",
    },
    {
        "provider": IntegrationProvider.MICROSOFT365,
        "label": "Microsoft 365",
        "description": "Analyze Outlook business conversations.",
    },
    {
        "provider": IntegrationProvider.DEMO,
        "label": "Demo WhatsApp",
        "description": "A simulated WhatsApp Business connector for local development and demonstration.",
    },
)


def list_channels(session: Session, business_id: uuid.UUID, settings: Settings | None = None) -> list[dict]:
    active = settings or get_settings()
    business = session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    rows = {
        row.provider: row
        for row in session.scalars(select(ChannelConnection).where(ChannelConnection.business_id == business_id)).all()
    }
    from app.integrations.gmail_push import gmail_realtime_fields

    listed = []
    for item in CATALOG:
        provider = item["provider"]
        row = rows.get(provider.value)
        realtime = {
            "listening": False,
            "realtime": "not_configured",
            "last_notification_at": None,
            "pubsub_configured": False,
        }
        last_error = None if row is None else row.last_error
        if provider is IntegrationProvider.GMAIL:
            extra = gmail_realtime_fields(row, active)
            last_error = extra.pop("last_error")
            realtime = extra
        listed.append(
            {
                "provider": provider.value,
                "label": item["label"],
                "description": item["description"],
                "availability": _availability(provider, row, active),
                "account_label": None if row is None else row.display_name or row.external_account_id,
                "connected_at": None if row is None else row.connected_at,
                "last_sync_at": None if row is None else row.last_sync_at,
                "last_error": last_error,
                "configured": _configured(provider, active),
                **realtime,
            }
        )
    return listed


def connect_whatsapp(
    session: Session,
    business_id: uuid.UUID,
    phone_number_id: str,
    display_name: str | None,
    settings: Settings | None = None,
    user_id: uuid.UUID | None = None,
) -> ChannelConnection:
    active = settings or get_settings()
    if not active.whatsapp_configured():
        raise ProviderError("Configuration required.")
    return save_connection(
        session,
        business_id=business_id,
        provider=IntegrationProvider.WHATSAPP,
        external_account_id=phone_number_id.strip(),
        display_name=(display_name or phone_number_id).strip(),
        metadata={"product": "whatsapp_cloud"},
        connected_by_user_id=user_id,
    )


def disconnect(session: Session, business_id: uuid.UUID, provider: IntegrationProvider) -> ChannelConnection:
    if provider is IntegrationProvider.DEMO:
        raise ProviderError("The demo connector is not a live account.")
    row = _require_connection(session, business_id, provider)
    row.status = ConnectionStatus.DISCONNECTED.value
    row.external_account_id = None
    row.connected_at = None
    secret = session.get(IntegrationCredential, row.id)
    if secret is not None:
        session.delete(secret)
    session.commit()
    return row


def save_connection(
    session: Session,
    *,
    business_id: uuid.UUID,
    provider: IntegrationProvider,
    external_account_id: str,
    display_name: str,
    metadata: dict | None = None,
    connected_by_user_id: uuid.UUID | None = None,
) -> ChannelConnection:
    if session.get(Business, business_id) is None:
        raise NotFoundError("Business not found.")
    owner = session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.provider == provider.value,
            ChannelConnection.external_account_id == external_account_id,
            ChannelConnection.status == ConnectionStatus.CONNECTED.value,
            ChannelConnection.business_id != business_id,
        )
    )
    if owner is not None:
        raise ConflictError("That account is already connected to another business.")
    row = session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.business_id == business_id,
            ChannelConnection.provider == provider.value,
        )
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = ChannelConnection(
            business_id=business_id,
            provider=provider.value,
            status=ConnectionStatus.CONNECTED.value,
            external_account_id=external_account_id,
            display_name=display_name,
            connected_at=now,
            connected_by_user_id=connected_by_user_id,
            connection_metadata=metadata,
        )
        session.add(row)
    else:
        row.status = ConnectionStatus.CONNECTED.value
        row.external_account_id = external_account_id
        row.display_name = display_name
        row.connected_at = now
        row.connected_by_user_id = connected_by_user_id
        row.last_error = None
        row.connection_metadata = metadata
    session.commit()
    return row


def store_credential(
    session: Session,
    connection: ChannelConnection,
    *,
    access_token: str,
    refresh_token: str | None,
    expires_at: datetime | None,
) -> None:
    secret = session.get(IntegrationCredential, connection.id)
    if secret is None:
        secret = IntegrationCredential(connection_id=connection.id)
        session.add(secret)
    secret.access_token = seal_secret(access_token)
    secret.refresh_token = seal_secret(refresh_token)
    secret.expires_at = expires_at
    session.commit()


def begin_oauth(
    session: Session,
    business_id: uuid.UUID,
    provider: IntegrationProvider,
    user_id: uuid.UUID,
) -> str:
    if provider not in (IntegrationProvider.GMAIL, IntegrationProvider.MICROSOFT365):
        raise ProviderError("This provider does not use OAuth.")
    if session.get(Business, business_id) is None:
        raise NotFoundError("Business not found.")
    if role_for(session, user_id, business_id) is None:
        raise ProviderError("Invalid or expired connection attempt.")
    token = secrets.token_urlsafe(32)
    session.add(
        OAuthState(
            state=token,
            business_id=business_id,
            provider=provider.value,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=get_settings().oauth_state_ttl_seconds),
        )
    )
    session.commit()
    return token


def consume_oauth_state(
    session: Session,
    state: str,
    provider: IntegrationProvider,
    expected_user_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    row = session.scalar(select(OAuthState).where(OAuthState.state == state, OAuthState.provider == provider.value))
    now = datetime.now(timezone.utc)
    if row is None or row.used_at is not None or row.expires_at <= now or row.user_id is None:
        raise ProviderError("Invalid or expired connection attempt.")
    if expected_user_id is not None and expected_user_id != row.user_id:
        raise ProviderError("Invalid or expired connection attempt.")
    if role_for(session, row.user_id, row.business_id) is None:
        raise ProviderError("Invalid or expired connection attempt.")
    row.used_at = now
    session.commit()
    return row.business_id, row.user_id


def plaintext_access_token(secret: IntegrationCredential | None) -> str:
    if secret is None or not secret.access_token:
        raise ProviderError("Configuration required.")
    opened = open_secret(secret.access_token)
    if not opened:
        raise ProviderError("Configuration required.")
    return opened


def require_connected(session: Session, business_id: uuid.UUID, provider: IntegrationProvider) -> ChannelConnection:
    row = session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.business_id == business_id,
            ChannelConnection.provider == provider.value,
            ChannelConnection.status == ConnectionStatus.CONNECTED.value,
        )
    )
    if row is None:
        raise NotFoundError("This channel is not connected.")
    return row


def find_connected_account(
    session: Session,
    provider: IntegrationProvider,
    external_account_id: str,
) -> ChannelConnection | None:
    return session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.provider == provider.value,
            ChannelConnection.external_account_id == external_account_id,
            ChannelConnection.status == ConnectionStatus.CONNECTED.value,
        )
    )


def mark_sync(session: Session, connection_id: uuid.UUID, error: str | None, *, failed: bool = False) -> None:
    row = session.get(ChannelConnection, connection_id)
    if row is None:
        return
    row.last_sync_at = datetime.now(timezone.utc)
    row.last_error = error
    if failed:
        row.status = ConnectionStatus.ERROR.value
    elif error is None and row.status == ConnectionStatus.ERROR.value:
        row.status = ConnectionStatus.CONNECTED.value
    session.commit()


def _require_connection(
    session: Session,
    business_id: uuid.UUID,
    provider: IntegrationProvider,
) -> ChannelConnection:
    row = session.scalar(
        select(ChannelConnection).where(
            ChannelConnection.business_id == business_id,
            ChannelConnection.provider == provider.value,
        )
    )
    if row is None:
        raise NotFoundError("This channel is not connected.")
    return row


def _configured(provider: IntegrationProvider, settings: Settings) -> bool:
    if provider is IntegrationProvider.WHATSAPP:
        return settings.whatsapp_configured()
    if provider is IntegrationProvider.GMAIL:
        return settings.gmail_configured()
    if provider is IntegrationProvider.MICROSOFT365:
        return settings.microsoft_configured()
    return settings.vigie_demo_mode


def _availability(provider: IntegrationProvider, row: ChannelConnection | None, settings: Settings) -> str:
    if provider is IntegrationProvider.DEMO:
        return "prototype" if settings.vigie_demo_mode else "not_configured"
    if row is not None and row.status == ConnectionStatus.CONNECTED.value:
        return "connected"
    if row is not None and row.status == ConnectionStatus.ERROR.value:
        return "error"
    if row is not None and row.status == ConnectionStatus.PENDING.value:
        return "pending"
    if row is not None and row.status == ConnectionStatus.DISCONNECTED.value:
        return "disconnected"
    if _configured(provider, settings):
        return "available"
    return "not_configured"
