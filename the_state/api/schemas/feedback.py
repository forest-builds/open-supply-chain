from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    brief_id: uuid.UUID
    acknowledged: bool = False
    action_taken: str | None = None
    false_positive: bool = False
    false_negative: bool = False
    notes: str | None = None
    outcome: str | None = None


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    brief_id: uuid.UUID | None
    watched_entity_id: uuid.UUID
    acknowledged: bool
    action_taken: str | None
    false_positive: bool
    false_negative: bool
    outcome: str | None
    logged_at: datetime

    model_config = {"from_attributes": True}
