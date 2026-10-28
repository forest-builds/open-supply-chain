from datetime import datetime, timedelta, timezone

from core.db import get_db
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from schemas.state import LocationStateHistoryEntry
from services.location_state_service import LocationStateService
from services.state_page_renderer import render_location_state_page
from sqlalchemy.ext.asyncio import AsyncSession
from state_products.location_state.schema import LocationState

router = APIRouter()


@router.get("/location", response_model=LocationState)
async def get_location_state(
    place: str = Query(..., description="Place string, e.g. 'New York, NY'"),
    time_window: str = Query(
        "24h", description="Window for active signals: e.g. '24h', '7d', '2w', '1m'"
    ),
    db: AsyncSession = Depends(get_db),
) -> LocationState:
    state = await LocationStateService(db).get_location_state(place=place, time_window=time_window)
    # Persist the append-only snapshot the service flushed.
    await db.commit()
    return state


@router.get("/location/history", response_model=list[LocationStateHistoryEntry])
async def get_location_state_history(
    place: str = Query(..., description="Place string, e.g. 'Brooklyn, NYC'"),
    from_dt: datetime | None = Query(None, description="ISO start; default 7d ago"),
    to_dt: datetime | None = Query(None, description="ISO end; default now"),
    limit: int = Query(48, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[LocationStateHistoryEntry]:
    now = datetime.now(timezone.utc)
    return await LocationStateService(db).get_location_state_history(
        place=place,
        from_dt=from_dt or (now - timedelta(days=7)),
        to_dt=to_dt or now,
        limit=limit,
    )


@router.get("/nyc", response_class=HTMLResponse)
async def get_nyc_state_page(db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    state = await LocationStateService(db).get_location_state(
        place="New York, NY",
        time_window="24h",
    )
    await db.commit()
    return HTMLResponse(render_location_state_page(state))
