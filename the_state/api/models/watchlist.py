import uuid
from datetime import datetime
from typing import Any

from core.db import Base
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    contact_email: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_sms: Mapped[str | None] = mapped_column(String, nullable=True)
    # evaluation cadence: "1h", "6h", "24h" etc.
    evaluation_cadence: Mapped[str] = mapped_column(String, nullable=False, server_default="24h")
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
