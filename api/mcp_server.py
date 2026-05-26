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


if __name__ == "__main__":
    mcp.run()
