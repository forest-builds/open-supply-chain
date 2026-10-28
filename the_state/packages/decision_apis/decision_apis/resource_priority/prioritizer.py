from dataclasses import dataclass
from enum import StrEnum


class ResourceType(StrEnum):
    PERSONNEL = "personnel"
    EQUIPMENT = "equipment"
    SUPPLIES = "supplies"
    SHELTER = "shelter"


@dataclass
class Resource:
    id: str
    type: ResourceType
    quantity: int
    location: str


@dataclass
class PriorityAssignment:
    resource_id: str
    incident_id: str
    priority: int  # 1 = highest
    rationale: str


class ResourcePrioritizer:
    """Assigns resources to incidents by priority."""

    async def prioritize(
        self,
        resources: list[Resource],
        incident_ids: list[str],
    ) -> list[PriorityAssignment]:
        # TODO: score incidents by risk, match resource types to needs
        return []
