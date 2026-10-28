from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ingestion.base import NormalizedSignal

__all__ = ["NormalizedSignal", "NycDatasetConfig", "NycDatasetName"]

NycDatasetName = Literal[
    "311",
    "dot_street_closures",
    "nyc_events",
    "hpd_violations",
    "nypd_collisions",
    "film_permits",
    "hpd_complaints",
    "dob_permits",
]


class NycDatasetConfig(BaseModel):
    name: NycDatasetName
    source_name: str
    dataset_id: str
    record_type: str
    date_field: str
    default_order: str
