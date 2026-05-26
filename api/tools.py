from __future__ import annotations

from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Query

from api.db import get_connection

tools_router = APIRouter(prefix="/tools", tags=["tools"])

EntityType = Literal["port", "facility", "route", "location", "aoi"]
TopologyRelation = Literal["intersects", "contains", "within", "touches", "crosses"]

GIS_METADATA = {
    "crs": {
        "srid": 4326,
        "epsg": "EPSG:4326",
        "name": "WGS 84",
        "geometry_column_srid": 4326,
        "geojson_crs_assumption": "GeoJSON coordinates are longitude/latitude in WGS 84.",
    },
    "coordinate_order": ["longitude", "latitude"],
    "geometry_format": "GeoJSON",
    "storage": "PostGIS geometry(Geometry, 4326)",
    "distance_units": {
        "radius_parameters": "kilometers unless named distance_m",
        "distance_properties": "kilometers for distance_km, meters for *_distance_m",
        "distance_calculation": "geography casts are used for meter/kilometer distance tools",
    },
    "topology_model": {
        "engine": "PostGIS",
        "supported_relations": ["intersects", "contains", "within", "touches", "crosses"],
        "bounded_queries": "Topology tools operate on persisted entity geometries, not raw table access.",
    },
}

_TOPOLOGY_PREDICATES = {
    "intersects": "ST_Intersects",
    "contains": "ST_Contains",
    "within": "ST_Within",
    "touches": "ST_Touches",
    "crosses": "ST_Crosses",
}

# ---------------------------------------------------------------------------
# Catalog — machine-readable tool discovery for MCP
# ---------------------------------------------------------------------------

TOOL_CATALOG = [
    {
        "name": "ports_near",
        "endpoint": "GET /tools/ports-near",
        "description": "Find ports within a radius of a lat/lon point, ordered by distance.",
        "parameters": {
            "lat": "float — center latitude",
            "lon": "float — center longitude",
            "radius_km": "float (default 50, max 500) — search radius in kilometers",
            "limit": "int (default 100, max 1000)",
        },
        "returns": "ToolResult with GeoJSON features including distance_km",
    },
    {
        "name": "facilities_near",
        "endpoint": "GET /tools/facilities-near",
        "description": "Find facilities (warehouses, storage tanks, industrial sites) within a radius. Filter by subtype.",
        "parameters": {
            "lat": "float — center latitude",
            "lon": "float — center longitude",
            "radius_km": "float (default 50, max 500)",
            "subtype": "str? — warehouse | storage_tank | logistics | industrial_site",
            "limit": "int (default 100, max 1000)",
        },
        "returns": "ToolResult with GeoJSON features including distance_km",
    },
    {
        "name": "weather_stations_near",
        "endpoint": "GET /tools/weather-stations-near",
        "description": "Find NOAA weather monitoring stations within a radius. Useful for climate/disruption risk queries.",
        "parameters": {
            "lat": "float — center latitude",
            "lon": "float — center longitude",
            "radius_km": "float (default 100, max 500)",
            "limit": "int (default 50, max 500)",
        },
        "returns": "ToolResult with GeoJSON features including distance_km and station metadata",
    },
    {
        "name": "stream_gauges_near",
        "endpoint": "GET /tools/stream-gauges-near",
        "description": "Find USGS stream/estuary/lake gauge sites within a radius. Useful for flood and waterway risk queries.",
        "parameters": {
            "lat": "float — center latitude",
            "lon": "float — center longitude",
            "radius_km": "float (default 100, max 500)",
            "limit": "int (default 50, max 500)",
        },
        "returns": "ToolResult with GeoJSON features including distance_km and gauge metadata",
    },
    {
        "name": "routes_near",
        "endpoint": "GET /tools/routes-near",
        "description": "Find transport routes (highway, rail, ferry, waterway) passing within a radius of a point.",
        "parameters": {
            "lat": "float — center latitude",
            "lon": "float — center longitude",
            "radius_km": "float (default 25, max 200)",
            "limit": "int (default 50, max 500)",
        },
        "returns": "ToolResult with GeoJSON LineString/Polygon features",
    },
    {
        "name": "entities_in_bbox",
        "endpoint": "GET /tools/entities-in-bbox",
        "description": "Return all supply chain entities within a bounding box. Optionally filter by entity type.",
        "parameters": {
            "min_lon": "float — western edge",
            "min_lat": "float — southern edge",
            "max_lon": "float — eastern edge",
            "max_lat": "float — northern edge",
            "entity_type": "str? — port | facility | route | location | aoi",
            "limit": "int (default 500, max 5000)",
        },
        "returns": "ToolResult with all matching GeoJSON features",
    },
    {
        "name": "search_entities",
        "endpoint": "GET /tools/search",
        "description": "Full-text search across entity names. Optionally filter by entity type.",
        "parameters": {
            "q": "str — search term (case-insensitive partial match)",
            "entity_type": "str? — port | facility | route | location | aoi",
            "limit": "int (default 20, max 200)",
        },
        "returns": "ToolResult with matching GeoJSON features ranked by name",
    },
    {
        "name": "gis_metadata",
        "endpoint": "GET /tools/gis-metadata",
        "description": "Return CRS, coordinate order, geometry format, units, and topology metadata for the GIS tool layer.",
        "parameters": {},
        "returns": "Metadata describing the GIS assumptions shared by API and MCP tools",
    },
    {
        "name": "layer_metadata",
        "endpoint": "GET /tools/layer-metadata",
        "description": "Summarize available GIS layers, feature counts, sources, and first/last seen timestamps.",
        "parameters": {},
        "returns": "Layer/source freshness summary grouped by entity_type and subtype",
    },
    {
        "name": "topology_relations_for_entity",
        "endpoint": "GET /tools/topology-relations-for-entity",
        "description": "Find persisted entities with a selected PostGIS topological relation to an anchor entity.",
        "parameters": {
            "entity_id": "uuid — anchor geo_entities.id",
            "relation": "str (default intersects) — intersects | contains | within | touches | crosses",
            "entity_type": "str? — optional result filter: port | facility | route | location | aoi",
            "limit": "int (default 100, max 1000)",
        },
        "returns": "ToolResult FeatureCollection with topology_relation on each feature",
    },
    {
        "name": "buffer_entity",
        "endpoint": "GET /tools/buffer-entity",
        "description": "Return a bounded buffer polygon around one persisted entity geometry.",
        "parameters": {
            "entity_id": "uuid — geo_entities.id",
            "distance_m": "float (default 1000, max 100000) — buffer distance in meters",
        },
        "returns": "FeatureCollection containing a derived buffer feature",
    },
    {
        "name": "assets_impacted_by_event",
        "endpoint": "GET /tools/assets-impacted-by-event",
        "description": "Return ports, facilities, and routes linked to a persisted risk event impact edge.",
        "parameters": {
            "event_id": "uuid — risk_events.id",
            "entity_type": "str? — port | facility | route",
            "limit": "int (default 500, max 5000)",
        },
        "returns": "ToolResult with impacted GeoJSON entities and impact evidence",
    },
    {
        "name": "risk_events_near_asset",
        "endpoint": "GET /tools/risk-events-near-asset",
        "description": "Return risk events linked to a supply-chain asset by the persisted impact network.",
        "parameters": {
            "entity_id": "uuid — geo_entities.id",
            "limit": "int (default 100, max 1000)",
        },
        "returns": "Risk event FeatureCollection with impact evidence",
    },
    {
        "name": "routes_impacted_by_alert",
        "endpoint": "GET /tools/routes-impacted-by-alert",
        "description": "Return route entities impacted by a specific risk event.",
        "parameters": {
            "event_id": "uuid — risk_events.id",
            "limit": "int (default 500, max 5000)",
        },
        "returns": "ToolResult with impacted route GeoJSON features",
    },
    {
        "name": "summarize_asset_exposure",
        "endpoint": "GET /tools/summarize-asset-exposure",
        "description": "Summarize persisted risk exposure for one supply-chain asset.",
        "parameters": {
            "entity_id": "uuid — geo_entities.id",
        },
        "returns": "Summary counts by severity/event type plus supporting events",
    },
    {
        "name": "trace_supply_chain",
        "endpoint": "GET /chains/connected",
        "description": "Find ports and facilities sharing a transportation corridor with a given entity ID.",
        "parameters": {
            "entity_id": "uuid — geo_entities.id",
            "limit": "int (default 30, max 500)",
        },
        "returns": "FeatureCollection with corridor peers, via_route_id, via_route_name, chain_confidence",
    },
    {
        "name": "find_chain_assets",
        "description": "Search for a named port or facility, then return corridor-connected supply chain peers.",
        "parameters": {
            "name": "str — partial name match",
            "entity_type": "str (default 'port') — port | facility",
            "limit": "int (default 30)",
        },
        "returns": "FeatureCollection of corridor-connected peers, or 'No entity found' message",
    },
    {
        "name": "example_refrigerated_food_port_newark",
        "endpoint": "GET /chains/examples/refrigerated-food-port-newark",
        "description": "Return a concrete worked supply-chain trace for refrigerated food imports through Port Newark.",
        "parameters": {
            "radius_km": "float (default 8, max 50) — vessel search radius around the anchor port",
            "limit": "int (default 10, max 100) — max facilities/vessels to return",
        },
        "returns": "Evidence-bearing chain example with anchor port, served routes, facility peers, vessels, flow steps, confidence, and limitations",
    },
]


@tools_router.get("/catalog")
def catalog() -> dict:
    """List all available deterministic spatial tools. Use this for MCP tool discovery."""
    return {
        "tool_count": len(TOOL_CATALOG),
        "tools": TOOL_CATALOG,
        "usage": "Each tool returns a ToolResult: {tool, parameters, count, features, sources, explanation, confidence}",
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _tool_result(
    tool: str,
    params: dict[str, Any],
    rows: list[dict[str, Any]],
    explanation: str,
    confidence: float = 0.85,
) -> dict[str, Any]:
    sources = sorted({r["source_name"] for r in rows if r.get("source_name")})
    features = []
    for r in rows:
        props: dict[str, Any] = {
            "entity_type": r["entity_type"],
            "subtype": r.get("subtype"),
            "name": r.get("name"),
            "source_name": r.get("source_name"),
            "confidence": r.get("confidence"),
        }
        if r.get("impact_method"):
            props["impact_method"] = r["impact_method"]
        if r.get("impact_confidence") is not None:
            props["impact_confidence"] = float(r["impact_confidence"])
        if r.get("impact_evidence"):
            props["impact_evidence"] = r["impact_evidence"]
        if r.get("distance_km") is not None:
            props["distance_km"] = round(float(r["distance_km"]), 3)
        if r.get("impact_distance_m") is not None:
            props["impact_distance_m"] = round(float(r["impact_distance_m"]), 3)
        if r.get("source_tags"):
            props["source_tags"] = r["source_tags"]
        features.append(
            {
                "type": "Feature",
                "id": r["id"],
                "properties": props,
                "geometry": r["geometry"],
            }
        )
    return {
        "tool": tool,
        "parameters": params,
        "count": len(features),
        "type": "FeatureCollection",
        "features": features,
        "sources": sources,
        "explanation": explanation,
        "confidence": confidence,
    }


def _point_select() -> str:
    return """
        SELECT
          id::text,
          entity_type,
          subtype,
          name,
          source_name,
          confidence::float,
          source_tags,
          ST_AsGeoJSON(geometry)::json AS geometry,
          ST_Distance(geometry::geography, ST_MakePoint(%s, %s)::geography) / 1000.0 AS distance_km
    """


def _nearest_label(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    r = rows[0]
    name = r.get("name") or "unnamed"
    dist = r.get("distance_km")
    return f" Nearest: {name} ({dist:.1f}km)." if dist is not None else f" Nearest: {name}."


def _risk_event_collection(
    tool: str,
    params: dict[str, Any],
    rows: list[dict[str, Any]],
    explanation: str,
    confidence: float = 0.85,
) -> dict[str, Any]:
    features = []
    for row in rows:
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "properties": {
                    "record_type": "risk_event",
                    "event_type": row["event_type"],
                    "severity": row["severity"],
                    "headline": row["headline"],
                    "area_desc": row["area_desc"],
                    "source_name": row["source_name"],
                    "source_event_id": row["source_event_id"],
                    "impact_method": row.get("impact_method"),
                    "impact_distance_m": row.get("impact_distance_m"),
                    "impact_confidence": row.get("impact_confidence"),
                    "impact_evidence": row.get("impact_evidence"),
                },
                "geometry": row["geometry"],
            }
        )
    return {
        "tool": tool,
        "parameters": params,
        "count": len(features),
        "type": "FeatureCollection",
        "features": features,
        "sources": sorted({r["source_name"] for r in rows if r.get("source_name")}),
        "explanation": explanation,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tools_router.get("/ports-near")
def ports_near(
    lat: Annotated[float, Query(description="Center latitude")],
    lon: Annotated[float, Query(description="Center longitude")],
    radius_km: Annotated[float, Query(ge=1, le=500, description="Search radius in km")] = 50,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict:
    """Find ports within a radius of a point, ordered by distance."""
    params = {"lat": lat, "lon": lon, "radius_km": radius_km, "limit": limit}
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                {_point_select()}
                FROM geo_entities
                WHERE entity_type = 'port'
                  AND ST_DWithin(geometry::geography, ST_MakePoint(%s, %s)::geography, %s)
                ORDER BY distance_km
                LIMIT %s
                """,
                (lon, lat, lon, lat, radius_km * 1000, limit),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    n = len(rows)
    explanation = (
        f"Found {n} port{'s' if n != 1 else ''} within {radius_km}km of ({lat:.4f}, {lon:.4f})."
        + _nearest_label(rows)
    )
    return _tool_result("ports_near", params, rows, explanation)


@tools_router.get("/facilities-near")
def facilities_near(
    lat: Annotated[float, Query(description="Center latitude")],
    lon: Annotated[float, Query(description="Center longitude")],
    radius_km: Annotated[float, Query(ge=1, le=500)] = 50,
    subtype: Annotated[
        str | None,
        Query(description="warehouse | storage_tank | logistics | industrial_site"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict:
    """Find facilities within a radius. Optionally filter by subtype."""
    params = {"lat": lat, "lon": lon, "radius_km": radius_km, "subtype": subtype, "limit": limit}
    extra_where = "AND subtype = %s" if subtype else ""
    extra_params = (subtype,) if subtype else ()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                {_point_select()}
                FROM geo_entities
                WHERE entity_type = 'facility'
                  AND ST_DWithin(geometry::geography, ST_MakePoint(%s, %s)::geography, %s)
                  {extra_where}
                ORDER BY distance_km
                LIMIT %s
                """,
                (lon, lat, lon, lat, radius_km * 1000) + extra_params + (limit,),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    n = len(rows)
    subtype_label = f" ({subtype})" if subtype else ""
    explanation = (
        f"Found {n} facilit{'ies' if n != 1 else 'y'}{subtype_label} within {radius_km}km "
        f"of ({lat:.4f}, {lon:.4f})." + _nearest_label(rows)
    )
    return _tool_result("facilities_near", params, rows, explanation)


@tools_router.get("/weather-stations-near")
def weather_stations_near(
    lat: Annotated[float, Query(description="Center latitude")],
    lon: Annotated[float, Query(description="Center longitude")],
    radius_km: Annotated[float, Query(ge=1, le=500)] = 100,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Find NOAA weather monitoring stations near a point."""
    params = {"lat": lat, "lon": lon, "radius_km": radius_km, "limit": limit}
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                {_point_select()}
                FROM geo_entities
                WHERE entity_type = 'location'
                  AND subtype = 'weather_station'
                  AND ST_DWithin(geometry::geography, ST_MakePoint(%s, %s)::geography, %s)
                ORDER BY distance_km
                LIMIT %s
                """,
                (lon, lat, lon, lat, radius_km * 1000, limit),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    n = len(rows)
    explanation = (
        f"Found {n} NOAA weather station{'s' if n != 1 else ''} within {radius_km}km "
        f"of ({lat:.4f}, {lon:.4f})." + _nearest_label(rows)
    )
    return _tool_result("weather_stations_near", params, rows, explanation)


@tools_router.get("/stream-gauges-near")
def stream_gauges_near(
    lat: Annotated[float, Query(description="Center latitude")],
    lon: Annotated[float, Query(description="Center longitude")],
    radius_km: Annotated[float, Query(ge=1, le=500)] = 100,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Find USGS stream gauge monitoring sites near a point."""
    params = {"lat": lat, "lon": lon, "radius_km": radius_km, "limit": limit}
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                {_point_select()}
                FROM geo_entities
                WHERE entity_type = 'location'
                  AND subtype = 'stream_gauge'
                  AND ST_DWithin(geometry::geography, ST_MakePoint(%s, %s)::geography, %s)
                ORDER BY distance_km
                LIMIT %s
                """,
                (lon, lat, lon, lat, radius_km * 1000, limit),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    n = len(rows)
    explanation = (
        f"Found {n} USGS stream gauge{'s' if n != 1 else ''} within {radius_km}km "
        f"of ({lat:.4f}, {lon:.4f})." + _nearest_label(rows)
    )
    return _tool_result("stream_gauges_near", params, rows, explanation)


@tools_router.get("/routes-near")
def routes_near(
    lat: Annotated[float, Query(description="Center latitude")],
    lon: Annotated[float, Query(description="Center longitude")],
    radius_km: Annotated[float, Query(ge=1, le=200)] = 25,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Find transport routes passing within a radius of a point."""
    params = {"lat": lat, "lon": lon, "radius_km": radius_km, "limit": limit}
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                {_point_select()}
                FROM geo_entities
                WHERE entity_type = 'route'
                  AND ST_DWithin(geometry::geography, ST_MakePoint(%s, %s)::geography, %s)
                ORDER BY distance_km
                LIMIT %s
                """,
                (lon, lat, lon, lat, radius_km * 1000, limit),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    n = len(rows)
    explanation = (
        f"Found {n} transport route{'s' if n != 1 else ''} within {radius_km}km "
        f"of ({lat:.4f}, {lon:.4f})."
    )
    return _tool_result("routes_near", params, rows, explanation)


@tools_router.get("/entities-in-bbox")
def entities_in_bbox(
    min_lon: Annotated[float, Query(description="Western edge")],
    min_lat: Annotated[float, Query(description="Southern edge")],
    max_lon: Annotated[float, Query(description="Eastern edge")],
    max_lat: Annotated[float, Query(description="Northern edge")],
    entity_type: Annotated[EntityType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> dict:
    """Return all supply chain entities within a bounding box."""
    params = {
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "entity_type": entity_type,
        "limit": limit,
    }
    type_where = "AND entity_type = %s" if entity_type else ""
    type_param = (entity_type,) if entity_type else ()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                  id::text, entity_type, subtype, name, source_name,
                  confidence::float, source_tags,
                  ST_AsGeoJSON(geometry)::json AS geometry
                FROM geo_entities
                WHERE ST_Intersects(
                  geometry,
                  ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                )
                {type_where}
                ORDER BY entity_type, name NULLS LAST
                LIMIT %s
                """,
                (min_lon, min_lat, max_lon, max_lat) + type_param + (limit,),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    n = len(rows)
    type_label = f" ({entity_type})" if entity_type else ""
    explanation = (
        f"Found {n} entit{'ies' if n != 1 else 'y'}{type_label} within bounding box "
        f"[{min_lon:.3f}, {min_lat:.3f}, {max_lon:.3f}, {max_lat:.3f}]."
    )
    return _tool_result("entities_in_bbox", params, rows, explanation)


@tools_router.get("/search")
def search_entities(
    q: Annotated[
        str,
        Query(min_length=1, description="Search term — case-insensitive partial match on name"),
    ],
    entity_type: Annotated[EntityType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> dict:
    """Search entities by name. Optionally filter by entity type."""
    params = {"q": q, "entity_type": entity_type, "limit": limit}
    type_where = "AND entity_type = %s" if entity_type else ""
    type_param = (entity_type,) if entity_type else ()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                  id::text, entity_type, subtype, name, source_name,
                  confidence::float, source_tags,
                  ST_AsGeoJSON(geometry)::json AS geometry
                FROM geo_entities
                WHERE name ILIKE %s
                {type_where}
                ORDER BY entity_type, name
                LIMIT %s
                """,
                (f"%{q}%",) + type_param + (limit,),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    n = len(rows)
    type_label = f" ({entity_type})" if entity_type else ""
    explanation = f'Found {n} entit{"ies" if n != 1 else "y"}{type_label} matching "{q}".'
    return _tool_result("search_entities", params, rows, explanation)


@tools_router.get("/gis-metadata")
def gis_metadata() -> dict[str, Any]:
    """Return CRS, units, and geometry assumptions for GIS clients."""
    return {
        "tool": "gis_metadata",
        "metadata": GIS_METADATA,
        "explanation": "All stored geometries use EPSG:4326 and GeoJSON longitude/latitude output.",
        "confidence": 1.0,
    }


@tools_router.get("/layer-metadata")
def layer_metadata() -> dict[str, Any]:
    """Summarize available GIS layers, sources, and freshness."""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                  entity_type,
                  subtype,
                  count(*)::int AS feature_count,
                  array_agg(DISTINCT source_name ORDER BY source_name) AS sources,
                  min(first_seen_at) AS first_seen_at,
                  max(last_seen_at) AS last_seen_at
                FROM geo_entities
                GROUP BY entity_type, subtype
                ORDER BY entity_type, subtype NULLS FIRST
                """
            ).fetchall()
            source_rows = conn.execute(
                """
                SELECT
                  s.name,
                  s.api_url,
                  s.license,
                  s.attribution,
                  s.refresh_rate,
                  count(ge.id)::int AS feature_count,
                  max(ge.last_seen_at) AS last_seen_at
                FROM sources s
                LEFT JOIN geo_entities ge ON ge.source_id = s.id
                GROUP BY s.id, s.name, s.api_url, s.license, s.attribution, s.refresh_rate
                ORDER BY feature_count DESC, s.name
                """
            ).fetchall()
    except psycopg.OperationalError:
        rows = []
        source_rows = []

    layers = [
        {
            "entity_type": row["entity_type"],
            "subtype": row["subtype"],
            "feature_count": row["feature_count"],
            "sources": row["sources"] or [],
            "first_seen_at": row["first_seen_at"].isoformat() if row["first_seen_at"] else None,
            "last_seen_at": row["last_seen_at"].isoformat() if row["last_seen_at"] else None,
            "crs": GIS_METADATA["crs"]["epsg"],
            "geometry_format": GIS_METADATA["geometry_format"],
        }
        for row in rows
    ]
    sources = [
        {
            "name": row["name"],
            "api_url": row["api_url"],
            "license": row["license"],
            "attribution": row["attribution"],
            "refresh_rate": row["refresh_rate"],
            "feature_count": row["feature_count"],
            "last_seen_at": row["last_seen_at"].isoformat() if row["last_seen_at"] else None,
        }
        for row in source_rows
    ]
    return {
        "tool": "layer_metadata",
        "layer_count": len(layers),
        "layers": layers,
        "source_count": len(sources),
        "sources": sources,
        "metadata": GIS_METADATA,
        "explanation": f"Found {len(layers)} GIS layer group{'s' if len(layers) != 1 else ''}.",
        "confidence": 0.95 if layers or sources else 0.5,
    }


@tools_router.get("/topology-relations-for-entity")
def topology_relations_for_entity(
    entity_id: Annotated[str, Query(description="Anchor geo_entities.id")],
    relation: Annotated[
        TopologyRelation,
        Query(description="intersects | contains | within | touches | crosses"),
    ] = "intersects",
    entity_type: Annotated[EntityType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict[str, Any]:
    """Find persisted entities with a selected topological relation to an anchor entity."""
    params = {
        "entity_id": entity_id,
        "relation": relation,
        "entity_type": entity_type,
        "limit": limit,
    }
    predicate = _TOPOLOGY_PREDICATES[relation]
    type_where = "AND ge.entity_type = %s" if entity_type else ""
    type_param = (entity_type,) if entity_type else ()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                WITH anchor AS (
                  SELECT id, geometry
                  FROM geo_entities
                  WHERE id = %s
                )
                SELECT
                  ge.id::text,
                  ge.entity_type,
                  ge.subtype,
                  ge.name,
                  ge.source_name,
                  ge.confidence::float,
                  ge.source_tags,
                  ST_AsGeoJSON(ge.geometry)::json AS geometry
                FROM anchor
                JOIN geo_entities ge
                  ON ge.id <> anchor.id
                 AND {predicate}(ge.geometry, anchor.geometry)
                WHERE true
                  {type_where}
                ORDER BY ge.entity_type, ge.name NULLS LAST
                LIMIT %s
                """,
                (entity_id,) + type_param + (limit,),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    features = []
    for row in rows:
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "properties": {
                    "entity_type": row["entity_type"],
                    "subtype": row.get("subtype"),
                    "name": row.get("name"),
                    "source_name": row.get("source_name"),
                    "confidence": row.get("confidence"),
                    "source_tags": row.get("source_tags"),
                    "topology_relation": relation,
                    "anchor_entity_id": entity_id,
                },
                "geometry": row["geometry"],
            }
        )
    return {
        "tool": "topology_relations_for_entity",
        "parameters": params,
        "count": len(features),
        "type": "FeatureCollection",
        "features": features,
        "sources": sorted({row["source_name"] for row in rows if row.get("source_name")}),
        "explanation": (
            f"Found {len(features)} entit{'ies' if len(features) != 1 else 'y'} "
            f"where geometry {relation} anchor entity {entity_id}."
        ),
        "confidence": 0.85 if features else 0.5,
        "metadata": {"crs": GIS_METADATA["crs"]["epsg"], "topology_engine": "PostGIS"},
    }


@tools_router.get("/buffer-entity")
def buffer_entity(
    entity_id: Annotated[str, Query(description="geo_entities.id")],
    distance_m: Annotated[float, Query(ge=1, le=100000)] = 1000,
) -> dict[str, Any]:
    """Return a derived buffer polygon around one persisted entity."""
    params = {"entity_id": entity_id, "distance_m": distance_m}
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                  id::text,
                  entity_type,
                  subtype,
                  name,
                  source_name,
                  confidence::float,
                  ST_AsGeoJSON(ST_Buffer(geometry::geography, %s)::geometry)::json AS geometry
                FROM geo_entities
                WHERE id = %s
                """,
                (distance_m, entity_id),
            ).fetchone()
    except psycopg.OperationalError:
        row = None

    features = []
    sources = []
    if row:
        sources = [row["source_name"]] if row.get("source_name") else []
        features.append(
            {
                "type": "Feature",
                "id": f"{row['id']}:buffer:{int(distance_m)}m",
                "properties": {
                    "record_type": "derived_buffer",
                    "entity_id": row["id"],
                    "entity_type": row["entity_type"],
                    "subtype": row.get("subtype"),
                    "name": row.get("name"),
                    "source_name": row.get("source_name"),
                    "confidence": row.get("confidence"),
                    "buffer_distance_m": distance_m,
                    "crs": GIS_METADATA["crs"]["epsg"],
                },
                "geometry": row["geometry"],
            }
        )

    return {
        "tool": "buffer_entity",
        "parameters": params,
        "count": len(features),
        "type": "FeatureCollection",
        "features": features,
        "sources": sources,
        "explanation": (
            f"Created {distance_m:g}m buffer for entity {entity_id}."
            if features
            else f"No entity found for {entity_id}; no buffer created."
        ),
        "confidence": 0.8 if features else 0.5,
        "metadata": {"crs": GIS_METADATA["crs"]["epsg"], "topology_engine": "PostGIS"},
    }


@tools_router.get("/assets-impacted-by-event")
def assets_impacted_by_event(
    event_id: Annotated[str, Query(description="risk_events.id")],
    entity_type: Annotated[Literal["port", "facility", "route"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> dict:
    params = {"event_id": event_id, "entity_type": entity_type, "limit": limit}
    type_where = "AND ge.entity_type = %s" if entity_type else ""
    type_param = (entity_type,) if entity_type else ()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                  ge.id::text,
                  ge.entity_type,
                  ge.subtype,
                  ge.name,
                  ge.source_name,
                  ge.confidence::float,
                  ge.source_tags,
                  ri.impact_method,
                  ri.distance_m::float AS impact_distance_m,
                  ri.confidence::float AS impact_confidence,
                  ri.evidence AS impact_evidence,
                  ST_AsGeoJSON(ge.geometry)::json AS geometry
                FROM risk_impacts ri
                JOIN geo_entities ge ON ge.id = ri.impacted_entity_id
                WHERE ri.risk_event_id = %s
                {type_where}
                ORDER BY ge.entity_type, ri.impact_method, ri.distance_m NULLS FIRST
                LIMIT %s
                """,
                (event_id,) + type_param + (limit,),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    type_label = f" {entity_type}" if entity_type else ""
    explanation = f"Found {len(rows)} impacted{type_label} asset{'s' if len(rows) != 1 else ''} for risk event {event_id}."
    return _tool_result("assets_impacted_by_event", params, rows, explanation)


@tools_router.get("/risk-events-near-asset")
def risk_events_near_asset(
    entity_id: Annotated[str, Query(description="geo_entities.id")],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict:
    params = {"entity_id": entity_id, "limit": limit}
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                  re.id::text,
                  re.event_type,
                  re.severity,
                  re.headline,
                  re.area_desc,
                  re.source_name,
                  re.source_event_id,
                  ri.impact_method,
                  ri.distance_m::float AS impact_distance_m,
                  ri.confidence::float AS impact_confidence,
                  ri.evidence AS impact_evidence,
                  ST_AsGeoJSON(re.geometry)::json AS geometry
                FROM risk_impacts ri
                JOIN risk_events re ON re.id = ri.risk_event_id
                WHERE ri.impacted_entity_id = %s
                ORDER BY
                  CASE re.severity
                    WHEN 'Extreme' THEN 1
                    WHEN 'Severe' THEN 2
                    WHEN 'Moderate' THEN 3
                    WHEN 'Minor' THEN 4
                    ELSE 5
                  END,
                  re.effective_at DESC NULLS LAST
                LIMIT %s
                """,
                (entity_id, limit),
            ).fetchall()
    except psycopg.OperationalError:
        rows = []

    explanation = (
        f"Found {len(rows)} risk event{'s' if len(rows) != 1 else ''} linked to asset {entity_id}."
    )
    return _risk_event_collection("risk_events_near_asset", params, rows, explanation)


@tools_router.get("/routes-impacted-by-alert")
def routes_impacted_by_alert(
    event_id: Annotated[str, Query(description="risk_events.id")],
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> dict:
    return assets_impacted_by_event(event_id=event_id, entity_type="route", limit=limit) | {
        "tool": "routes_impacted_by_alert"
    }


def trace_supply_chain(entity_id: str, limit: int = 30) -> dict[str, Any]:
    """Return corridor-connected ports/facilities sharing a route with entity_id."""
    from api.chains import chain_connected_rows  # noqa: PLC0415

    params = {"entity_id": entity_id, "limit": limit}
    rows = chain_connected_rows(entity_id, limit)
    features = []
    sources: list[str] = []
    for r in rows:
        if r.get("source_name") and r["source_name"] not in sources:
            sources.append(r["source_name"])
        features.append(
            {
                "type": "Feature",
                "id": r["id"],
                "properties": {
                    "entity_type": r["entity_type"],
                    "subtype": r.get("subtype"),
                    "name": r.get("name"),
                    "source_name": r.get("source_name"),
                    "confidence": r.get("confidence"),
                    "chain_confidence": r.get("chain_confidence"),
                    "via_route_id": r.get("via_route_id"),
                    "via_route_name": r.get("via_route_name"),
                    "via_route_subtype": r.get("via_route_subtype"),
                },
                "geometry": r["geometry"],
            }
        )
    n = len(features)
    return {
        "tool": "trace_supply_chain",
        "parameters": params,
        "count": n,
        "type": "FeatureCollection",
        "features": features,
        "sources": sorted(set(sources)),
        "explanation": f"{n} asset{'s' if n != 1 else ''} share a transportation corridor with entity {entity_id}.",
        "confidence": 0.75,
    }


def find_chain_assets(name: str, entity_type: str = "port", limit: int = 30) -> dict[str, Any]:
    """Search for a named entity then return its corridor-connected peers."""
    anchor = search_entities(q=name, entity_type=entity_type, limit=1)  # type: ignore[arg-type]
    if anchor["count"] == 0:
        return {
            "tool": "find_chain_assets",
            "parameters": {"name": name, "entity_type": entity_type, "limit": limit},
            "count": 0,
            "type": "FeatureCollection",
            "features": [],
            "sources": [],
            "explanation": f"No entity named '{name}' found.",
            "confidence": 0.5,
        }
    found_id = anchor["features"][0]["id"]
    result = trace_supply_chain(found_id, limit)
    result["tool"] = "find_chain_assets"
    result["parameters"] = {"name": name, "entity_type": entity_type, "limit": limit}
    return result


def example_refrigerated_food_port_newark(radius_km: float = 8, limit: int = 10) -> dict[str, Any]:
    """Return the concrete refrigerated-food-through-Port-Newark chain example."""
    from api.chains import refrigerated_food_port_newark_chain  # noqa: PLC0415

    result = refrigerated_food_port_newark_chain(radius_km=radius_km, limit=limit)
    result["tool"] = "example_refrigerated_food_port_newark"
    return result


@tools_router.get("/summarize-asset-exposure")
def summarize_asset_exposure(
    entity_id: Annotated[str, Query(description="geo_entities.id")],
) -> dict:
    params = {"entity_id": entity_id}
    try:
        with get_connection() as conn:
            asset = conn.execute(
                """
                SELECT id::text, entity_type, subtype, name, source_name
                FROM geo_entities
                WHERE id = %s
                """,
                (entity_id,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT
                  re.severity,
                  re.event_type,
                  ri.impact_method,
                  count(*)::int AS count
                FROM risk_impacts ri
                JOIN risk_events re ON re.id = ri.risk_event_id
                WHERE ri.impacted_entity_id = %s
                GROUP BY re.severity, re.event_type, ri.impact_method
                ORDER BY re.severity, re.event_type, ri.impact_method
                """,
                (entity_id,),
            ).fetchall()
    except psycopg.OperationalError:
        asset = None
        rows = []

    total = sum(row["count"] for row in rows)
    return {
        "tool": "summarize_asset_exposure",
        "parameters": params,
        "asset": asset,
        "count": total,
        "type": "FeatureCollection",
        "features": [],
        "exposure_summary": rows,
        "sources": ["risk_impacts"] if rows else [],
        "explanation": f"Asset {entity_id} is linked to {total} persisted risk impact{'s' if total != 1 else ''}.",
        "confidence": 0.85 if rows else 0.5,
    }
