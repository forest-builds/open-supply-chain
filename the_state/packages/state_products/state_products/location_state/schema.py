from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class OperationalState(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    WATCH = "watch"
    DISRUPTED = "disrupted"
    CRITICAL = "critical"


class ActiveSignal(BaseModel):
    signal_id: UUID
    signal_type: str
    source: str
    severity: str | None = None
    title: str | None = None
    occurred_at: datetime | None = None
    contribution: float = Field(..., ge=0.0, le=1.0)


class Driver(BaseModel):
    label: str
    weight: float = Field(..., ge=0.0, le=1.0)
    signal_ids: list[UUID] = Field(default_factory=list)


class RecentChange(BaseModel):
    occurred_at: datetime
    description: str
    signal_id: UUID | None = None


class Recommendation(BaseModel):
    action: str
    rationale: str | None = None


class Provenance(BaseModel):
    signal_id: UUID
    source: str
    raw_record_id: UUID | None = None
    contribution: float = Field(..., ge=0.0, le=1.0)
    observed_at: datetime | None = None


class SubLocationState(BaseModel):
    name: str  # "BROOKLYN", "10036", "Williamsburg"
    granularity: str  # "borough" | "zip" | "nta"
    operational_state: OperationalState
    risk_score: float = Field(..., ge=0.0, le=1.0)
    signal_count: int = Field(..., ge=0)


class LocationState(BaseModel):
    place: str
    state_code: str | None = None
    time_window: str
    operational_state: OperationalState
    risk_score: float = Field(..., ge=0.0, le=1.0)
    summary: str
    drivers: list[Driver] = Field(default_factory=list)
    active_signals: list[ActiveSignal] = Field(default_factory=list)
    recent_changes: list[RecentChange] = Field(default_factory=list)
    recommended_actions: list[Recommendation] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    provenance: list[Provenance] = Field(default_factory=list)
    sub_locations: list[SubLocationState] = Field(default_factory=list)
    computed_at: datetime
