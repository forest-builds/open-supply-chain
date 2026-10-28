from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator
from state_products.location_state.schema import LocationState, OperationalState


class WatchlistThresholds(BaseModel):
    notify_on_state: list[str] = Field(default_factory=lambda: ["watch", "disrupted", "critical"])
    min_score_delta: float = Field(default=0.15, ge=0.0, le=1.0)


class WatchlistDelivery(BaseModel):
    channels: list[str] = Field(default_factory=list)
    webhook_url: str | None = None


class WatchlistCreate(BaseModel):
    name: str
    # `places` is the real field. `place` (singular) is kept for backward
    # compatibility with existing API consumers and is folded into `places`.
    places: list[str] = Field(default_factory=list)
    place: str | None = None
    time_window: str = "24h"
    thresholds: WatchlistThresholds = Field(default_factory=WatchlistThresholds)
    delivery: WatchlistDelivery = Field(default_factory=WatchlistDelivery)

    @model_validator(mode="after")
    def _coalesce_places(self) -> WatchlistCreate:
        if not self.places and self.place is not None:
            self.places = [self.place]
        if not self.places:
            raise ValueError("watchlist requires at least one place")
        return self


class WatchlistResponse(BaseModel):
    id: uuid.UUID
    name: str
    # `place` mirrors `places[0]` so single-place consumers keep working.
    place: str
    places: list[str]
    time_window: str
    thresholds: WatchlistThresholds
    delivery: WatchlistDelivery
    created_at: datetime
    updated_at: datetime


class EntityEvaluationResult(BaseModel):
    watched_entity_id: uuid.UUID
    evaluation_result_id: uuid.UUID
    place: str
    previous_state: str | None
    current_state: str
    previous_score: float | None
    current_score: float
    score_delta: float | None
    material_change: bool
    location_state: LocationState


class WatchlistEvaluationResponse(BaseModel):
    id: uuid.UUID
    watchlist_id: uuid.UUID
    # Rollup across every watched place: the highest severity wins.
    operational_state: OperationalState
    evaluated_at: datetime
    entities: list[EntityEvaluationResult]
    # Backward-compatible single-entity view, populated from the
    # highest-severity entity so existing single-place consumers keep working.
    previous_state: str | None
    current_state: str
    previous_score: float | None
    current_score: float
    score_delta: float | None
    material_change: bool
    location_state: LocationState
