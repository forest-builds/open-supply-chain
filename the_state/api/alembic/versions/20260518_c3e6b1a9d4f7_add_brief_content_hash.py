"""add brief content hash (credentialing)

Revision ID: c3e6b1a9d4f7
Revises: b2d5a8c1f3e4
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3e6b1a9d4f7"
down_revision: str | None = "b2d5a8c1f3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("briefs", sa.Column("content_hash", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("briefs", "content_hash")
