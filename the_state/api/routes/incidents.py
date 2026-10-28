from core.db import get_db
from fastapi import APIRouter, Depends, Query
from schemas.incident import IncidentListResponse, IncidentResponse
from services.incident_service import IncidentService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=IncidentListResponse)
async def list_incidents(
    state: str | None = Query(None, description="Filter by US state code (e.g. CA, TX)"),
    incident_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    svc = IncidentService(db)
    return await svc.list_incidents(
        state=state,
        incident_type=incident_type,
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    svc = IncidentService(db)
    return await svc.get_incident(incident_id)
