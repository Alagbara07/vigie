import logging

import httpx

from app.domain.errors import ProviderError
from app.integrations.oauth_log import prefix

logger = logging.getLogger(__name__)

_UNAVAILABLE = "The provider could not complete the connection."


def post_form(url: str, data: dict[str, str], *, purpose: str = "provider") -> dict:
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(url, data=data)
    except httpx.HTTPError:
        logger.warning("%sProvider request failed purpose=%s status=none code=transport", prefix(), purpose)
        raise ProviderError(_UNAVAILABLE) from None
    return _object(response, purpose)


def get_json(url: str, access_token: str, *, purpose: str = "provider") -> dict:
    try:
        with httpx.Client(timeout=20) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError:
        logger.warning("%sProvider request failed purpose=%s status=none code=transport", prefix(), purpose)
        raise ProviderError(_UNAVAILABLE) from None
    return _object(response, purpose)


def _object(response: httpx.Response, purpose: str) -> dict:
    if response.status_code >= 400:
        logger.warning(
            "%sProvider request failed purpose=%s status=%s code=%s",
            prefix(),
            purpose,
            response.status_code,
            _error_code(response),
        )
        raise ProviderError(_UNAVAILABLE)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(_UNAVAILABLE) from exc
    if not isinstance(payload, dict):
        raise ProviderError(_UNAVAILABLE)
    return payload


def _error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "unreadable"
    if not isinstance(payload, dict):
        return "unreadable"
    error = payload.get("error")
    if isinstance(error, dict):
        error = error.get("code")
    if isinstance(error, str) and _safe_code(error):
        return error
    return "unknown"


def _safe_code(value: str) -> bool:
    return value.isascii() and " " not in value and 1 <= len(value) <= 80
