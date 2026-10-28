from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, model_validator


class GetCurrentStateInput(BaseModel):
    place: str = Field(..., examples=["New York, NY"])
    time_window: str = Field(default="24h", examples=["24h"])


class GenerateOperationalBriefInput(BaseModel):
    watchlist_id: uuid.UUID | None = None
    watched_entity_id: uuid.UUID | None = None
    evaluation_result_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def require_source(self) -> "GenerateOperationalBriefInput":
        if (
            self.watchlist_id is None
            and self.watched_entity_id is None
            and self.evaluation_result_id is None
        ):
            raise ValueError("Provide watchlist_id, watched_entity_id, or evaluation_result_id")
        return self


class WatchEntityInput(BaseModel):
    name: str
    place: str = Field(..., examples=["New York, NY"])
    time_window: str = "24h"
    thresholds: dict[str, Any] | None = None
    delivery: dict[str, Any] | None = None


MCP_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_current_state": {
        "description": "Return current deterministic LocationState for a place.",
        "input_schema": GetCurrentStateInput.model_json_schema(),
    },
    "generate_operational_brief": {
        "description": "Generate a deterministic operational brief from state/provenance.",
        "input_schema": GenerateOperationalBriefInput.model_json_schema(),
    },
    "watch_entity": {
        "description": "Create a v0 location watchlist for repeated evaluation.",
        "input_schema": WatchEntityInput.model_json_schema(),
    },
}


def list_tool_schemas() -> dict[str, dict[str, Any]]:
    return MCP_TOOL_SCHEMAS
