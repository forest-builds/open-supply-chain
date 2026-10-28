"""add brief canonical url

Revision ID: b2d5a8c1f3e4
Revises: a1c4f7b9e2d0
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d5a8c1f3e4"
down_revision: str | None = "a1c4f7b9e2d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("briefs", sa.Column("url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("briefs", "url")
