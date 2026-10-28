import uuid
from datetime import datetime
from typing import Any

from core.db import Base
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class StateEvaluationResult(Base):
    __tablename__ = "state_evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    watched_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watched_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    previous_state: Mapped[str | None] = mapped_column(String, nullable=True)
    current_state: Mapped[str] = mapped_column(String, nullable=False)
    previous_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_score: Mapped[float] = mapped_column(Float, nullable=False)
    score_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    # True when state band changed or score_delta exceeds threshold
    material_change: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    drivers: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provenance: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    recommended_actions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
