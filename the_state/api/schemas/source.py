import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SourceCreate(BaseModel):
    name: str
    source_type: str
    base_url: str | None = None
    description: str | None = None
    meta: dict[str, Any] = {}


class SourceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    source_type: str
    base_url: str | None
    description: str | None
    meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int
