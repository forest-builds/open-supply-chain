from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class BriefGenerateRequest(BaseModel):
    watchlist_id: uuid.UUID | None = None
    watched_entity_id: uuid.UUID | None = None
    evaluation_result_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def require_source(self) -> "BriefGenerateRequest":
        if (
            self.watchlist_id is None
            and self.watched_entity_id is None
            and self.evaluation_result_id is None
        ):
            raise ValueError("Provide watchlist_id, watched_entity_id, or evaluation_result_id")
        return self


class BriefResponse(BaseModel):
    id: uuid.UUID
    watched_entity_id: uuid.UUID
    evaluation_result_id: uuid.UUID | None
    title: str
    place: str
    operational_state: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    summary: str
    what_changed: str
    why_it_matters: str
    recommended_actions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    confidence: float = Field(..., ge=0.0, le=1.0)
    content: str
    generated_at: datetime
    url: str
    content_hash: str

    model_config = {"from_attributes": True}


class BriefVerification(BaseModel):
    """A self-contained, publicly checkable attestation for one brief.

    The point: a caller does not have to trust us. They can recompute the
    digest from `content` themselves and confirm it equals `computed_hash`.
    """

    brief_id: uuid.UUID
    algorithm: str = "sha256"
    stored_hash: str | None
    computed_hash: str
    verified: bool
    content_length: int
    generated_at: datetime
    verified_at: datetime
    canonical_url: str
