"""City-agnostic ingestion contract.

Every city integration produces the same ``NormalizedSignal`` shape and
satisfies ``NormalizerProtocol``. Nothing here is NYC-specific — this is the
seam that lets the platform scale to new cities without touching the core
pipeline. See ``packages/ingestion/CONTRIBUTING.md`` for the contributor guide.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class NormalizedSignal(BaseModel):
    """The single shape the rest of the pipeline consumes.

    A city normalizer's only job is to turn one source record into one of
    these. ``source_type`` defaults to the NYC reference value; new cities
    pass their own (e.g. ``"chicago_open_data"``).
    """

    source_name: str
    source_type: str = "nyc_open_data"
    external_id: str
    record_type: str
    payload: dict[str, Any]
    signal_type: str
    title: str
    summary: str | None = None
    severity: str | None = None
    occurred_at: datetime | None = None
    observed_at: datetime
    location: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class NormalizerProtocol(Protocol):
    """Contract a city normalizer must satisfy.

    ``dataset_name`` selects which of the city's datasets the raw ``record``
    came from; the implementation returns a single ``NormalizedSignal``.
    """

    def normalize_record(self, dataset_name: str, record: dict[str, Any]) -> NormalizedSignal: ...
