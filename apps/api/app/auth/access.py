import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import MemberRole
from app.models import Business, Membership


def role_for(session: Session, user_id: uuid.UUID, business_id: uuid.UUID) -> MemberRole | None:
    row = session.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.business_id == business_id)
    )
    if row is None:
        return None
    return MemberRole(row.role)


def ensure_membership(
    session: Session,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
    role: MemberRole,
) -> Membership:
    row = session.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.business_id == business_id)
    )
    if row is not None:
        return row
    row = Membership(user_id=user_id, business_id=business_id, role=role.value)
    session.add(row)
    session.commit()
    return row


def memberships_for(session: Session, user_id: uuid.UUID) -> list[tuple[Business, Membership]]:
    rows = session.execute(
        select(Business, Membership)
        .join(Membership, Membership.business_id == Business.id)
        .where(Membership.user_id == user_id)
        .order_by(Business.created_at.asc(), Business.id.asc())
    ).all()
    return [(business, membership) for business, membership in rows]
