from datetime import datetime

from core.db import Base
from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column


class ScoringWeightCache(Base):
    """Materialized FeedbackLog calibration, keyed by (signal_type, severity).

    Avoids a full FeedbackLog scan on every scoring request. Refreshed by
    ``scoring_calibration_service.refresh_weight_cache``.
    """

    __tablename__ = "scoring_weight_cache"

    signal_type: Mapped[str] = mapped_column(String, primary_key=True)
    severity: Mapped[str] = mapped_column(String, primary_key=True)
    # Feedback-adjusted deterministic weight (replaces SCORING_WEIGHTS pair).
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    # Posterior reliability in [0,1]; feeds the confidence calibration term.
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    false_positive_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    confirmed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
