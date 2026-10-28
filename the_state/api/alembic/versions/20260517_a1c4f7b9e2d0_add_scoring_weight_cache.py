"""add scoring weight cache

Revision ID: a1c4f7b9e2d0
Revises: 56e1e9cadf66
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4f7b9e2d0"
down_revision: str | None = "56e1e9cadf66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scoring_weight_cache",
        sa.Column("signal_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("false_positive_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confirmed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("signal_type", "severity"),
    )


def downgrade() -> None:
    op.drop_table("scoring_weight_cache")
