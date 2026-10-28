from dataclasses import dataclass


@dataclass
class Sitrep:
    incident_id: str
    summary: str
    situation: str
    current_conditions: str
    resource_status: str | None = None
    weather_impact: str | None = None


class SitrepGenerator:
    """Generates situation reports for active incidents."""

    async def generate(
        self,
        incident_id: str,
        include_resources: bool = True,
        include_weather: bool = True,
    ) -> Sitrep:
        # TODO: pull incident data, resource status, weather overlays
        return Sitrep(
            incident_id=incident_id,
            summary="",
            situation="",
            current_conditions="",
            resource_status=None if not include_resources else "",
            weather_impact=None if not include_weather else "",
        )
