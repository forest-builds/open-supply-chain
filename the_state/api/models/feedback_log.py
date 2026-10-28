import uuid
from datetime import datetime

from core.db import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class FeedbackLog(Base):
    __tablename__ = "feedback_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    brief_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("briefs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    watched_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watched_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    action_taken: Mapped[str | None] = mapped_column(String, nullable=True)
    false_positive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    false_negative: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
