import uuid
from datetime import datetime

from core.db import Base
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    watched_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watched_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluation_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_evaluation_results.id", ondelete="SET NULL"), nullable=True
    )
    # Deterministic markdown content; LLM-enhanced when available
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Canonical permanent public path, set at creation: /briefs/{id}/view
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    # SHA-256 of the canonical content, set at creation, never updated.
    # Re-hashing the brief content must reproduce this - tamper-evident.
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
