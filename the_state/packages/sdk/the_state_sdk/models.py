"""Lean client-side mirrors of the API schemas.

These intentionally declare only the stable, documented fields and allow
extras (``model_config = {"extra": "allow"}``). The API contract is additive,
so an older SDK keeps working when the server adds fields — new data is still
accessible via attribute access, it just is not typed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="allow")


class LocationState(_Lenient):
    place: str
    state_code: str | None = None
    time_window: str
    operational_state: str
    risk_score: float
    summary: str
    drivers: list[dict[str, Any]] = []
    active_signals: list[dict[str, Any]] = []
    confidence: float
    provenance: list[dict[str, Any]] = []
    sub_locations: list[dict[str, Any]] = []
    computed_at: datetime


class Brief(_Lenient):
    id: str
    place: str
    operational_state: str
    risk_score: float
    summary: str
    content: str
    confidence: float
    generated_at: datetime
    url: str


class Watchlist(_Lenient):
    id: str
    name: str
    place: str
    places: list[str] = []
    time_window: str
