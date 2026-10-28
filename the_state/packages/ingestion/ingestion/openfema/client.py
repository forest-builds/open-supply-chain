import httpx
from pydantic import BaseModel


class FEMADisasterDeclaration(BaseModel):
    disasterNumber: int
    declarationTitle: str
    declarationType: str
    state: str
    incidentType: str
    declarationDate: str | None
    disasterCloseoutDate: str | None


class OpenFEMAClient:
    BASE_URL = "https://www.fema.gov/api/open/v2"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or self.BASE_URL

    async def get_disaster_declarations(
        self,
        state: str | None = None,
        incident_type: str | None = None,
        top: int = 100,
        skip: int = 0,
    ) -> list[FEMADisasterDeclaration]:
        params: dict = {"$top": top, "$skip": skip, "$format": "json"}
        filters = []
        if state:
            filters.append(f"state eq '{state}'")
        if incident_type:
            filters.append(f"incidentType eq '{incident_type}'")
        if filters:
            params["$filter"] = " and ".join(filters)

        async with httpx.AsyncClient(base_url=self.base_url) as client:
            resp = await client.get("/DisasterDeclarationsSummaries", params=params)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("DisasterDeclarationsSummaries", [])
            return [FEMADisasterDeclaration(**record) for record in records]
