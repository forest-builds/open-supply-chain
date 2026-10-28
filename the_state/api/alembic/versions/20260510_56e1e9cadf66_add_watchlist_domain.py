"""add watchlist domain

Revision ID: 56e1e9cadf66
Revises: f3a8c1d2
Create Date: 2026-05-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "56e1e9cadf66"
down_revision: str | None = "f3a8c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("contact_email", sa.String(), nullable=True),
        sa.Column("contact_sms", sa.String(), nullable=True),
        sa.Column("evaluation_cadence", sa.String(), server_default="24h", nullable=False),
        sa.Column(
            "meta",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_watchlists_owner", "watchlists", ["owner"])

    op.create_table(
        "watched_entities",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("watchlist_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_ref", sa.String(), nullable=False),
        sa.Column(
            "threshold_rules",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "delivery_preferences",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notified_state", sa.String(), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_watched_entities_watchlist_id", "watched_entities", ["watchlist_id"])
    op.create_index("ix_watched_entities_entity_type", "watched_entities", ["entity_type"])

    op.create_table(
        "state_evaluation_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("watched_entity_id", sa.UUID(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_state", sa.String(), nullable=True),
        sa.Column("current_state", sa.String(), nullable=False),
        sa.Column("previous_score", sa.Float(), nullable=True),
        sa.Column("current_score", sa.Float(), nullable=False),
        sa.Column("score_delta", sa.Float(), nullable=True),
        sa.Column("material_change", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "drivers",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "recommended_actions",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["watched_entity_id"],
            ["watched_entities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_state_evaluation_results_watched_entity_id",
        "state_evaluation_results",
        ["watched_entity_id"],
    )
    op.create_index(
        "ix_state_evaluation_results_evaluated_at",
        "state_evaluation_results",
        ["evaluated_at"],
    )

    op.create_table(
        "briefs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("watched_entity_id", sa.UUID(), nullable=False),
        sa.Column("evaluation_result_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["watched_entity_id"],
            ["watched_entities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_result_id"],
            ["state_evaluation_results.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_briefs_watched_entity_id", "briefs", ["watched_entity_id"])

    op.create_table(
        "feedback_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("brief_id", sa.UUID(), nullable=True),
        sa.Column("watched_entity_id", sa.UUID(), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("action_taken", sa.String(), nullable=True),
        sa.Column("false_positive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("false_negative", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column(
            "logged_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brief_id"], ["briefs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["watched_entity_id"],
            ["watched_entities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_logs_brief_id", "feedback_logs", ["brief_id"])
    op.create_index(
        "ix_feedback_logs_watched_entity_id",
        "feedback_logs",
        ["watched_entity_id"],
    )


def downgrade() -> None:
    op.drop_table("feedback_logs")
    op.drop_table("briefs")
    op.drop_table("state_evaluation_results")
    op.drop_table("watched_entities")
    op.drop_table("watchlists")
