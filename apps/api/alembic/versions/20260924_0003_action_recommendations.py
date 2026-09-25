"""Action labels and one recommendation per signal and type.

Revision ID: 20260924_0003
Revises: 20260924_0002
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0003"
down_revision: str | None = "20260924_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("actions", sa.Column("title", sa.String(200), nullable=True))
    op.add_column("actions", sa.Column("description", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_actions_signal_type",
        "actions",
        ["business_id", "signal_id", "action_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_actions_signal_type", "actions", type_="unique")
    op.drop_column("actions", "description")
    op.drop_column("actions", "title")
