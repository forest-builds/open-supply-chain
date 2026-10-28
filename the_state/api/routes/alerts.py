from fastapi import APIRouter, Query
from services.alert_service import AlertService

router = APIRouter()


@router.get("/")
async def list_alerts(
    area: str | None = Query(None, description="State or zone code"),
    severity: str | None = Query(None, description="Extreme, Severe, Moderate, Minor"),
):
    svc = AlertService()
    return await svc.list_active_alerts(area=area, severity=severity)
