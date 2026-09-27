from fastapi import Response

from app.core.config import get_settings

SESSION_COOKIE = "vigie_session"
BUSINESS_COOKIE = "vigie_business"


def apply_session_cookies(response: Response, token: str, business_id: str | None) -> None:
    options = _options()
    response.set_cookie(SESSION_COOKIE, token, max_age=get_settings().session_ttl_seconds, **options)
    if business_id is not None:
        response.set_cookie(BUSINESS_COOKIE, business_id, max_age=get_settings().session_ttl_seconds, **options)


def set_business_cookie(response: Response, business_id: str) -> None:
    response.set_cookie(
        BUSINESS_COOKIE,
        business_id,
        max_age=get_settings().session_ttl_seconds,
        **_options(),
    )


def clear_session_cookies(response: Response) -> None:
    options = _options()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=bool(options["secure"]), samesite="lax")
    response.delete_cookie(BUSINESS_COOKIE, path="/", secure=bool(options["secure"]), samesite="lax")


def _options() -> dict[str, object]:
    return {
        "httponly": True,
        "secure": get_settings().cookies_are_secure(),
        "samesite": "lax",
        "path": "/",
    }
