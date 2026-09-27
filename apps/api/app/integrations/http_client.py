import httpx

from app.domain.errors import ProviderError

_UNAVAILABLE = "The provider could not complete the connection."


def post_form(url: str, data: dict[str, str]) -> dict:
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(url, data=data)
    except httpx.HTTPError as exc:
        raise ProviderError(_UNAVAILABLE) from exc
    return _object(response)


def get_json(url: str, access_token: str) -> dict:
    try:
        with httpx.Client(timeout=20) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError as exc:
        raise ProviderError(_UNAVAILABLE) from exc
    return _object(response)


def _object(response: httpx.Response) -> dict:
    if response.status_code >= 400:
        raise ProviderError(_UNAVAILABLE)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(_UNAVAILABLE) from exc
    if not isinstance(payload, dict):
        raise ProviderError(_UNAVAILABLE)
    return payload
