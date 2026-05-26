from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from api import tools as spatial_tools
from api.chat import _geocode

EntityType = Literal["port", "facility", "route", "location", "aoi"]
TopologyRelation = Literal["intersects", "contains", "within", "touches", "crosses"]

mcp = FastMCP(
    name="Open Supply Chain",
    instructions=(
        "Use these governed tools to query open supply-chain geography, monitoring "
        "sites, and routes. The tools return evidence-bearing GeoJSON-style results "
        "from the existing Open Supply Chain API handlers; do not infer raw database "
        "state outside these responses."
    ),
)


@mcp.tool(
    name="geocode",
    description=(
        "Convert a US place name or address to latitude and longitude. Call this first "
        "when a user gives a named location instead of coordinates."
    ),
    tags={"geocoding", "location"},
    annotations={"readOnlyHint": True},
)
def geocode(query: str) -> dict[str, Any]:
    """Convert a US place name or address to coordinates."""
    return _geocode(query)


@mcp.tool(
    name="ports_near",
    description="Find ports within a radius of a latitude/longitude point, ordered by distance.",
    tags={"spatial", "ports"},
    annotations={"readOnlyHint": True},
)
def ports_near(
    lat: float,
    lon: float,
    radius_km: float = 50,
    limit: int = 100,
) -> dict[str, Any]:
    """Find ports near a point."""
    return spatial_tools.ports_near(lat=lat, lon=lon, radius_km=radius_km, limit=limit)


@mcp.tool(
    name="facilities_near",
    description=(
        "Find facilities such as warehouses, storage tanks, logistics sites, and "
        "industrial sites within a radius of a latitude/longitude point."
    ),
    tags={"spatial", "facilities"},
    annotations={"readOnlyHint": True},
)
def facilities_near(
    lat: float,
    lon: float,
    radius_km: float = 50,
    subtype: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Find facilities near a point, optionally filtered by subtype."""
    return spatial_tools.facilities_near(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        subtype=subtype,
        limit=limit,
    )


@mcp.tool(
    name="weather_stations_near",
    description="Find NOAA weather monitoring stations within a radius of a point.",
    tags={"spatial", "weather", "monitoring"},
    annotations={"readOnlyHint": True},
)
def weather_stations_near(
    lat: float,
    lon: float,
    radius_km: float = 100,
    limit: int = 50,
) -> dict[str, Any]:
    """Find NOAA weather stations near a point."""
    return spatial_tools.weather_stations_near(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=limit,
    )


@mcp.tool(
    name="stream_gauges_near",
    description=(
        "Find USGS stream, estuary, and lake gauge sites within a radius of a point. "
        "Use for flood risk, waterway, and river queries."
    ),
    tags={"spatial", "water", "monitoring"},
    annotations={"readOnlyHint": True},
)
def stream_gauges_near(
    lat: float,
    lon: float,
    radius_km: float = 100,
    limit: int = 50,
) -> dict[str, Any]:
    """Find USGS stream gauges near a point."""
    return spatial_tools.stream_gauges_near(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=limit,
    )


@mcp.tool(
    name="routes_near",
    description=(
        "Find transport routes such as highway, rail, ferry, and waterway features "
        "passing within a radius of a latitude/longitude point."
    ),
    tags={"spatial", "routes"},
    annotations={"readOnlyHint": True},
)
def routes_near(
    lat: float,
    lon: float,
    radius_km: float = 25,
    limit: int = 50,
) -> dict[str, Any]:
    """Find transport routes near a point."""
    return spatial_tools.routes_near(lat=lat, lon=lon, radius_km=radius_km, limit=limit)


@mcp.tool(
    name="entities_in_bbox",
    description=(
        "Return supply-chain entities inside a bounding box. Optionally filter by "
        "entity type: port, facility, route, location, or aoi."
    ),
    tags={"spatial", "search"},
    annotations={"readOnlyHint": True},
)
def entities_in_bbox(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    entity_type: EntityType | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Return supply-chain entities inside a bounding box."""
    return spatial_tools.entities_in_bbox(
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        entity_type=entity_type,
        limit=limit,
    )


@mcp.tool(
    name="search_entities",
    description=(
        "Search supply-chain entities by name with an optional entity type filter. "
        "Use when a user asks about a specific named port, facility, route, or place."
    ),
    tags={"search"},
    annotations={"readOnlyHint": True},
)
def search_entities(
    q: str,
    entity_type: EntityType | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search supply-chain entities by name."""
    return spatial_tools.search_entities(q=q, entity_type=entity_type, limit=limit)


@mcp.tool(
    name="gis_metadata",
    description=(
        "Return CRS, coordinate order, geometry format, units, and topology metadata "
        "for the Open Supply Chain GIS tool layer."
    ),
    tags={"gis", "metadata", "crs"},
    annotations={"readOnlyHint": True},
)
def gis_metadata() -> dict[str, Any]:
    """Return CRS, units, and geometry assumptions for GIS clients."""
    return spatial_tools.gis_metadata()


@mcp.tool(
    name="layer_metadata",
    description=(
        "Summarize available GIS layers, feature counts, sources, and first/last "
        "seen timestamps so agents can understand coverage before querying."
    ),
    tags={"gis", "metadata", "layers", "sources"},
    annotations={"readOnlyHint": True},
)
def layer_metadata() -> dict[str, Any]:
    """Return GIS layer and source metadata."""
    return spatial_tools.layer_metadata()


@mcp.tool(
    name="topology_relations_for_entity",
    description=(
        "Find persisted entities with a selected PostGIS topological relation to "
        "an anchor entity. Supported relations: intersects, contains, within, "
        "touches, crosses."
    ),
    tags={"gis", "topology", "spatial"},
    annotations={"readOnlyHint": True},
)
def topology_relations_for_entity(
    entity_id: str,
    relation: TopologyRelation = "intersects",
    entity_type: EntityType | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Find entities with a topological relation to an anchor entity."""
    return spatial_tools.topology_relations_for_entity(
        entity_id=entity_id,
        relation=relation,
        entity_type=entity_type,
        limit=limit,
    )


@mcp.tool(
    name="buffer_entity",
    description="Return a bounded derived buffer polygon around one persisted entity geometry.",
    tags={"gis", "topology", "buffer"},
    annotations={"readOnlyHint": True},
)
def buffer_entity(entity_id: str, distance_m: float = 1000) -> dict[str, Any]:
    """Return a derived buffer polygon around one persisted entity."""
    return spatial_tools.buffer_entity(entity_id=entity_id, distance_m=distance_m)


@mcp.tool(
    name="example_refrigerated_food_port_newark",
    description=(
        "Return a concrete worked supply-chain trace for refrigerated food imports "
        "through Port Newark: observed vessels, anchor port, served routes, and "
        "nearby cold/logistics facility peers."
    ),
    tags={"supply-chain", "example", "ports", "vessels"},
    annotations={"readOnlyHint": True},
)
def example_refrigerated_food_port_newark(radius_km: float = 8, limit: int = 10) -> dict[str, Any]:
    """Return the Port Newark refrigerated-food chain example."""
    return spatial_tools.example_refrigerated_food_port_newark(radius_km=radius_km, limit=limit)


@mcp.tool(
    name="risk_events_near_asset",
    description=(
        "Return risk events linked to a supply-chain asset through the persisted impact network. "
        "Shows NOAA alerts, earthquakes, and other hazards overlapping or near the asset, "
        "ordered by severity then recency."
    ),
    tags={"risk", "alerts", "supply-chain"},
    annotations={"readOnlyHint": True},
)
def risk_events_near_asset(entity_id: str, limit: int = 100) -> dict[str, Any]:
    """Return risk events linked to a supply-chain asset."""
    return spatial_tools.risk_events_near_asset(entity_id=entity_id, limit=limit)


@mcp.tool(
    name="assets_impacted_by_event",
    description=(
        "Return ports, facilities, and routes linked to a persisted risk event via the impact network. "
        "Answers: 'what supply-chain assets does this storm, earthquake, or alert affect?'"
    ),
    tags={"risk", "impact", "supply-chain"},
    annotations={"readOnlyHint": True},
)
def assets_impacted_by_event(
    event_id: str,
    entity_type: Literal["port", "facility", "route"] | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Return assets impacted by a risk event."""
    return spatial_tools.assets_impacted_by_event(event_id=event_id, entity_type=entity_type, limit=limit)


@mcp.tool(
    name="summarize_asset_exposure",
    description=(
        "Summarize total persisted risk exposure for one supply-chain asset: counts by severity, "
        "event type, and impact method. Use to triage which assets carry the most risk."
    ),
    tags={"risk", "exposure", "supply-chain"},
    annotations={"readOnlyHint": True},
)
def summarize_asset_exposure(entity_id: str) -> dict[str, Any]:
    """Summarize risk exposure counts for one asset."""
    return spatial_tools.summarize_asset_exposure(entity_id=entity_id)


@mcp.tool(
    name="trace_supply_chain",
    description=(
        "Find ports and facilities that share a transportation corridor with a given entity. "
        "Returns corridor-connected peers via the SERVED_BY_ROUTE graph with route names and chain confidence."
    ),
    tags={"supply-chain", "graph", "corridors"},
    annotations={"readOnlyHint": True},
)
def trace_supply_chain(entity_id: str, limit: int = 30) -> dict[str, Any]:
    """Return corridor-connected supply-chain peers."""
    return spatial_tools.trace_supply_chain(entity_id=entity_id, limit=limit)


@mcp.tool(
    name="find_chain_assets",
    description=(
        "Search for a named port or facility, then return all corridor-connected supply-chain peers. "
        "Combines name search with graph traversal in one call — no UUID required."
    ),
    tags={"supply-chain", "search", "graph"},
    annotations={"readOnlyHint": True},
)
def find_chain_assets(name: str, entity_type: str = "port", limit: int = 30) -> dict[str, Any]:
    """Search by name then return corridor-connected peers."""
    return spatial_tools.find_chain_assets(name=name, entity_type=entity_type, limit=limit)


@mcp.tool(
    name="active_alerts_near",
    description=(
        "Return non-expired active risk events (NOAA weather alerts, USGS earthquakes, GDACS disasters) "
        "within a radius of a point, ordered by severity then distance. "
        "Primary tool for real-time hazard awareness at any location."
    ),
    tags={"risk", "alerts", "live", "spatial"},
    annotations={"readOnlyHint": True},
)
def active_alerts_near(
    lat: float,
    lon: float,
    radius_km: float = 100,
    min_severity: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Return active (non-expired) risk events near a point."""
    return spatial_tools.active_alerts_near(
        lat=lat, lon=lon, radius_km=radius_km, min_severity=min_severity, limit=limit
    )


@mcp.tool(
    name="risk_events_near",
    description=(
        "Return risk events within a radius with optional filters for data source "
        "(noaa_nws_alerts, usgs_earthquakes, gdacs), active-only status, and minimum severity. "
        "Use for historical event analysis or cross-source comparison."
    ),
    tags={"risk", "events", "spatial", "historical"},
    annotations={"readOnlyHint": True},
)
def risk_events_near(
    lat: float,
    lon: float,
    radius_km: float = 100,
    source: str | None = None,
    active_only: bool = False,
    min_severity: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return risk events near a point with optional filters."""
    return spatial_tools.risk_events_near(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        source=source,
        active_only=active_only,
        min_severity=min_severity,
        limit=limit,
    )


@mcp.tool(
    name="vessels_near",
    description=(
        "Find AIS-tracked vessels near a point. Returns cargo ships, tankers, passenger vessels, "
        "and other AIS-reporting ships with their type, name, and last reported position. "
        "Use for maritime situational awareness and port activity monitoring."
    ),
    tags={"maritime", "vessels", "ais", "spatial"},
    annotations={"readOnlyHint": True},
)
def vessels_near(
    lat: float,
    lon: float,
    radius_km: float = 25,
    ship_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Find AIS vessels near a point, optionally filtered by ship type."""
    return spatial_tools.vessels_near(
        lat=lat, lon=lon, radius_km=radius_km, ship_type=ship_type, limit=limit
    )


@mcp.tool(
    name="corridor_risk_exposure",
    description=(
        "Return active risk events affecting an entity AND all its supply-chain corridor peers in one call. "
        "Each event shows which corridor assets it impacts. "
        "The primary tool for answering 'what threats does my entire supply-chain network face right now?' — "
        "combines SERVED_BY_ROUTE graph traversal, impact network lookup, and live alert filtering."
    ),
    tags={"supply-chain", "risk", "graph", "live", "network"},
    annotations={"readOnlyHint": True},
)
def corridor_risk_exposure(
    entity_id: str,
    active_only: bool = True,
    limit: int = 100,
) -> dict[str, Any]:
    """Return risk events affecting an entity and all its corridor peers."""
    return spatial_tools.corridor_risk_exposure(
        entity_id=entity_id, active_only=active_only, limit=limit
    )


if __name__ == "__main__":
    mcp.run()
