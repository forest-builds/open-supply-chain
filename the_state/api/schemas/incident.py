from datetime import datetime

from pydantic import BaseModel


class IncidentResponse(BaseModel):
    id: str
    incident_number: str
    title: str
    incident_type: str
    state: str
    declared_date: datetime | None
    close_date: datetime | None
    status: str


class IncidentListResponse(BaseModel):
    items: list[IncidentResponse]
    total: int
    offset: int
    limit: int
