from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.domain.errors import ProviderError

_PREFIX = "fernet:"


def seal_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if value.startswith(_PREFIX):
        return value
    token = _fernet().encrypt(value.encode()).decode()
    return _PREFIX + token


def open_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not value.startswith(_PREFIX):
        raise ProviderError("Stored credential is not readable.")
    try:
        return _fernet().decrypt(value[len(_PREFIX) :].encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise ProviderError("Stored credential is not readable.") from exc


def _fernet() -> Fernet:
    key = get_settings().credential_encryption_key.strip()
    if not key:
        raise ProviderError("Credential encryption is not configured.")
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise ProviderError("Credential encryption is not configured.") from exc
