import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.access import ensure_membership, memberships_for, role_for
from app.auth.cookies import apply_session_cookies, clear_session_cookies, set_business_cookie
from app.auth.deps import Principal, require_user
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import issue_session, revoke_session, session_token
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.enums import MemberRole
from app.models import Business, User
from app.schemas.auth import (
    CurrentBusinessRequest,
    LoginRequest,
    MembershipBusinessRead,
    SessionRead,
    SignupRequest,
    UserRead,
)
from app.seed.demo import DEMO_SLUG
from app.services.audit import record_audit

router = APIRouter(prefix="/api/auth")

DEMO_USER_EMAIL = "demo@vigie.local"


def session_view(session: Session, user: User, current_id: uuid.UUID | None) -> SessionRead:
    businesses = [
        MembershipBusinessRead(
            id=business.id,
            name=business.name,
            slug=business.slug,
            timezone=business.timezone,
            default_currency=business.default_currency,
            role=membership.role,
        )
        for business, membership in memberships_for(session, user.id)
    ]
    current = next((item for item in businesses if item.id == current_id), None)
    if current is None and businesses:
        current = businesses[0]
    return SessionRead(
        user=UserRead(id=user.id, email=user.email, name=user.name),
        businesses=businesses,
        current_business=current,
    )


def selected_business_id(request: Request, session: Session, user: User) -> uuid.UUID | None:
    from app.auth.cookies import BUSINESS_COOKIE

    raw = request.cookies.get(BUSINESS_COOKIE)
    if raw:
        try:
            candidate = uuid.UUID(raw)
        except ValueError:
            candidate = None
        if candidate is not None and role_for(session, user.id, candidate) is not None:
            return candidate
    rows = memberships_for(session, user.id)
    if not rows:
        return None
    return rows[0][0].id


@router.post("/signup", response_model=SessionRead, status_code=201)
def post_signup(payload: SignupRequest, response: Response, session: Session = Depends(get_db)) -> SessionRead:
    user = User(email=payload.email, name=payload.name, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    token = issue_session(session, user.id)
    apply_session_cookies(response, token, None)
    return session_view(session, user, None)


@router.post("/login", response_model=SessionRead)
def post_login(payload: LoginRequest, response: Response, session: Session = Depends(get_db)) -> SessionRead:
    user = session.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = issue_session(session, user.id)
    record_audit(
        session,
        user_id=user.id,
        business_id=None,
        action="login",
        resource_type="user",
        resource_id=str(user.id),
    )
    rows = memberships_for(session, user.id)
    current = rows[0][0].id if rows else None
    apply_session_cookies(response, token, str(current) if current else None)
    return session_view(session, user, current)


@router.post("/logout", status_code=204)
def post_logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_user),
    session: Session = Depends(get_db),
) -> None:
    del principal
    revoke_session(session, session_token(request.cookies))
    clear_session_cookies(response)


@router.get("/session", response_model=SessionRead)
def get_session(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_user),
    session: Session = Depends(get_db),
) -> SessionRead:
    current = selected_business_id(request, session, principal.user)
    if current is not None:
        set_business_cookie(response, str(current))
    return session_view(session, principal.user, current)


@router.post("/current-business", response_model=SessionRead)
def post_current_business(
    payload: CurrentBusinessRequest,
    response: Response,
    principal: Principal = Depends(require_user),
    session: Session = Depends(get_db),
) -> SessionRead:
    if role_for(session, principal.user.id, payload.business_id) is None:
        raise HTTPException(status_code=403, detail="You do not have access to this business.")
    set_business_cookie(response, str(payload.business_id))
    return session_view(session, principal.user, payload.business_id)


@router.post("/demo", response_model=SessionRead)
def post_demo(response: Response, session: Session = Depends(get_db)) -> SessionRead:
    if not get_settings().vigie_demo_mode:
        raise HTTPException(status_code=404, detail="Not found.")
    business = session.scalar(select(Business).where(Business.slug == DEMO_SLUG))
    if business is None:
        raise HTTPException(status_code=404, detail="The demo business has not been loaded.")
    user = session.scalar(select(User).where(User.email == DEMO_USER_EMAIL))
    if user is None:
        user = User(
            email=DEMO_USER_EMAIL,
            name="Demo",
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        session.add(user)
        session.commit()
    ensure_membership(session, user.id, business.id, MemberRole.OWNER)
    token = issue_session(session, user.id)
    record_audit(
        session,
        user_id=user.id,
        business_id=business.id,
        action="login",
        resource_type="user",
        resource_id=str(user.id),
        metadata={"demo": True},
    )
    apply_session_cookies(response, token, str(business.id))
    return session_view(session, user, business.id)
