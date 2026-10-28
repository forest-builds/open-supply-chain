import httpx
from core.config import settings


class AlertService:
    def __init__(self):
        self.base_url = settings.noaa_base_url

    async def list_active_alerts(self, area: str | None, severity: str | None) -> dict:
        params: dict = {"status": "actual"}
        if area:
            params["area"] = area
        if severity:
            params["severity"] = severity

        async with httpx.AsyncClient(base_url=self.base_url) as client:
            resp = await client.get("/alerts/active", params=params)
            resp.raise_for_status()
            return resp.json()
