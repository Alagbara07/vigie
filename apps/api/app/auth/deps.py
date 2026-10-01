import json
import logging
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.access import memberships_for, role_for
from app.auth.cookies import BUSINESS_COOKIE, SESSION_COOKIE
from app.auth.sessions import session_token, user_from_request_token
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.enums import MemberRole
from app.models import Business, User

_RANK = {MemberRole.MEMBER: 1, MemberRole.ADMIN: 2, MemberRole.OWNER: 3}
logger = logging.getLogger(__name__)
_FETCH_SITES = {"cross-site", "same-site", "same-origin", "none"}


@dataclass
class Principal:
    user: User
    business_id: uuid.UUID | None
    role: str | None


def reject_cross_site(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if not request.cookies.get(SESSION_COOKIE):
        return
    origin = request.headers.get("origin")
    if not origin:
        return
    if _origin_is_allowed(origin):
        return
    # Browsers set Sec-Fetch-Site and pages cannot override it. same-origin is the
    # Vercel app calling its own /api proxy. A cross-site page cannot send it.
    fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if fetch_site == "same-origin":
        return
    logger.warning(
        "Cross-site request blocked path=%s sec_fetch_site=%s origin_host=%s",
        request.url.path,
        fetch_site if fetch_site in _FETCH_SITES else "other",
        _origin_host(origin),
    )
    raise HTTPException(status_code=403, detail="Cross-site request blocked.")


def _origin_is_allowed(origin: str) -> bool:
    presented = _canonical_origin(origin)
    if not presented:
        return False
    return presented in {_canonical_origin(item) for item in get_settings().allowed_web_origins()}


def _canonical_origin(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    if "://" not in cleaned:
        return cleaned.lower()
    scheme, rest = cleaned.split("://", 1)
    scheme = scheme.lower()
    host = rest.split("/", 1)[0].split("@")[-1].lower()
    if scheme == "https" and host.endswith(":443"):
        host = host[:-4]
    if scheme == "http" and host.endswith(":80"):
        host = host[:-3]
    return f"{scheme}://{host}"


def _origin_host(origin: str) -> str:
    canonical = _canonical_origin(origin)
    if "://" not in canonical:
        return "invalid"
    return canonical.split("://", 1)[1][:200]


async def require_user(request: Request, session: Session = Depends(get_db)) -> Principal:
    reject_cross_site(request)
    user = user_from_request_token(session, session_token(request.cookies))
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return Principal(user=user, business_id=None, role=None)


async def require_member(request: Request, session: Session = Depends(get_db)) -> Principal:
    principal = await require_user(request, session)
    business_id = await requested_business_id(request)
    if business_id is None:
        business_id = _selected_business_id(request, session, principal.user.id)
    if business_id is None:
        raise HTTPException(status_code=409, detail="Create a business first.")
    if session.get(Business, business_id) is None:
        raise HTTPException(status_code=404, detail="Business not found.")
    role = role_for(session, principal.user.id, business_id)
    if role is None:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")
    return Principal(user=principal.user, business_id=business_id, role=role.value)


def require_role(minimum: MemberRole):
    def dependency(principal: Principal = Depends(require_member)) -> Principal:
        current = MemberRole(principal.role) if principal.role else None
        if current is None or _RANK[current] < _RANK[minimum]:
            raise HTTPException(status_code=403, detail="You do not have permission for this.")
        return principal

    return dependency


require_admin = require_role(MemberRole.ADMIN)


async def requested_business_id(request: Request) -> uuid.UUID | None:
    found: list[uuid.UUID] = []
    for raw in (request.path_params.get("business_id"), request.query_params.get("business_id")):
        parsed = _parse_uuid(raw)
        if raw not in (None, "") and parsed is None:
            raise HTTPException(status_code=422, detail="business_id is not valid.")
        if parsed is not None:
            found.append(parsed)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and "application/json" in request.headers.get(
        "content-type", ""
    ):
        raw_body = await request.body()
        if raw_body:
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("business_id") is not None:
                parsed = _parse_uuid(payload.get("business_id"))
                if parsed is None:
                    raise HTTPException(status_code=422, detail="business_id is not valid.")
                found.append(parsed)
    if len(set(found)) > 1:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")
    return found[0] if found else None


def _selected_business_id(request: Request, session: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    raw = request.cookies.get(BUSINESS_COOKIE)
    if raw:
        parsed = _parse_uuid(raw)
        if parsed is not None and role_for(session, user_id, parsed) is not None:
            return parsed
    rows = memberships_for(session, user_id)
    if not rows:
        return None
    return rows[0][0].id


def _parse_uuid(value: object) -> uuid.UUID | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
