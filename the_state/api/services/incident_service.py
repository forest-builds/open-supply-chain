from models.incident import Incident
from schemas.incident import IncidentListResponse, IncidentResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class IncidentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_incidents(
        self,
        state: str | None,
        incident_type: str | None,
        limit: int,
        offset: int,
    ) -> IncidentListResponse:
        q = select(Incident)
        if state:
            q = q.where(Incident.state == state.upper())
        if incident_type:
            q = q.where(Incident.incident_type == incident_type)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        rows = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return IncidentListResponse(
            items=[self._to_response(r) for r in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get_incident(self, incident_id: str) -> IncidentResponse:
        row = await self.db.get(Incident, incident_id)
        if not row:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Incident not found")
        return self._to_response(row)

    def _to_response(self, row: Incident) -> IncidentResponse:
        return IncidentResponse(
            id=row.id,
            incident_number=row.incident_number,
            title=row.title,
            incident_type=row.incident_type,
            state=row.state,
            declared_date=row.declared_date,
            close_date=row.close_date,
            status=row.status,
        )
