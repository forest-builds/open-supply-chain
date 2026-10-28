from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LocationStateHistoryEntry(BaseModel):
    """One immutable point in a place's state timeline."""

    computed_at: datetime
    operational_state: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    signal_count: int = Field(..., ge=0)
