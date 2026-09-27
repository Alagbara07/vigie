import logging

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import Settings, get_settings
from app.domain.errors import ProviderError

logger = logging.getLogger(__name__)

_FAILED = "Pub/Sub authentication failed."
_UNCONFIGURED = "Pub/Sub is not configured."


def verify_pubsub_push(authorization: str | None, settings: Settings | None = None) -> None:
    """Confirm a Google-signed OIDC token for this push endpoint.

    The bearer token is not logged. A missing Pub/Sub configuration rejects the
    request instead of accepting an unsigned mailbox notification.
    """
    active = settings or get_settings()
    if not active.gmail_pubsub_configured():
        raise ProviderError(_UNCONFIGURED)
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise ProviderError(_FAILED)
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise ProviderError(_FAILED)
    try:
        claims = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=active.resolved_gmail_pubsub_audience(),
        )
    except Exception as exc:
        logger.info("Gmail Pub/Sub token was rejected")
        raise ProviderError(_FAILED) from exc
    email = str(claims.get("email") or "").strip().lower()
    if claims.get("email_verified") is not True or email != active.gmail_pubsub_service_account.strip().lower():
        raise ProviderError(_FAILED)
