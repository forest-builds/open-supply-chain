import uuid
from datetime import datetime
from typing import Any

from core.db import Base
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class WatchedEntity(Base):
    __tablename__ = "watched_entities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "location" is the only supported type in v0
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # For locations: the place string ("New York, NY")
    entity_ref: Mapped[str] = mapped_column(String, nullable=False)
    # {"min_state": "elevated", "min_score_delta": 0.10}
    threshold_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    # {"email": true, "sms": false, "webhook": null}
    delivery_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_notified_state: Mapped[str | None] = mapped_column(String, nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
