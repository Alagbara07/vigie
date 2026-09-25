"""One commitment per source message and commitment type.

Revision ID: 20260924_0002
Revises: 20260924_0001
Create Date: 2026-09-24

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260924_0002"
down_revision: str | None = "20260924_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_commitments_source_type",
        "commitments",
        ["business_id", "source_message_id", "commitment_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_commitments_source_type", "commitments", type_="unique")
