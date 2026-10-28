from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class EntityStatus(StrEnum):
    OPEN = "open"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


@dataclass
class EntityState:
    entity_id: str
    entity_type: str = "generic"
    status: EntityStatus = EntityStatus.OPEN
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def incident_id(self) -> str:
        """Backward-compatible alias for the original incident-focused API."""
        return self.entity_id

    def transition(self, new_status: EntityStatus) -> None:
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)


IncidentStatus = EntityStatus
IncidentState = EntityState


class StateEngine:
    """Tracks and transitions operational entity states."""

    def __init__(self) -> None:
        self._states: dict[str, EntityState] = {}

    def get(self, entity_id: str) -> EntityState | None:
        return self._states.get(entity_id)

    def upsert(
        self,
        entity_id: str,
        entity_type: str = "generic",
        **metadata: Any,
    ) -> EntityState:
        if entity_id not in self._states:
            self._states[entity_id] = EntityState(
                entity_id=entity_id,
                entity_type=entity_type,
                metadata=metadata,
            )
        else:
            self._states[entity_id].entity_type = entity_type
            self._states[entity_id].metadata.update(metadata)
        return self._states[entity_id]

    def transition(self, entity_id: str, status: EntityStatus) -> EntityState:
        state = self._states.get(entity_id)
        if not state:
            raise KeyError(f"No state for entity {entity_id!r}")
        state.transition(status)
        return state
