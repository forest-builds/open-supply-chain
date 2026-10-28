import httpx
from pydantic import BaseModel


class NOAAAlert(BaseModel):
    id: str
    event: str
    severity: str
    urgency: str
    areas: list[str]
    headline: str | None
    description: str | None
    effective: str
    expires: str


class NOAAClient:
    BASE_URL = "https://api.weather.gov"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or self.BASE_URL
        self._headers = {"User-Agent": "the-state/0.1 (contact@thestate.dev)"}

    async def get_active_alerts(
        self,
        area: str | None = None,
        severity: str | None = None,
    ) -> list[NOAAAlert]:
        params: dict = {"status": "actual"}
        if area:
            params["area"] = area
        if severity:
            params["severity"] = severity

        async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers) as client:
            resp = await client.get("/alerts/active", params=params)
            resp.raise_for_status()
            features = resp.json().get("features", [])
            return [self._parse_alert(f) for f in features]

    def _parse_alert(self, feature: dict) -> NOAAAlert:
        props = feature.get("properties", {})
        return NOAAAlert(
            id=feature.get("id", ""),
            event=props.get("event", ""),
            severity=props.get("severity", "Unknown"),
            urgency=props.get("urgency", "Unknown"),
            areas=props.get("areaDesc", "").split("; "),
            headline=props.get("headline"),
            description=props.get("description"),
            effective=props.get("effective", ""),
            expires=props.get("expires", ""),
        )
