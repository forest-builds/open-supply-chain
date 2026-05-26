from __future__ import annotations

import json
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Query

from api.db import get_connection

chains_router = APIRouter(prefix="/chains", tags=["chains"])

_CONNECTED_SQL = """
WITH served_routes AS (
  SELECT object_entity_id AS route_id
  FROM entity_relationships
  WHERE subject_entity_id = %s
    AND relationship_type = 'SERVED_BY_ROUTE'
),
corridor_peers AS (
  SELECT DISTINCT
    er.subject_entity_id AS peer_id,
    er.object_entity_id  AS via_route_id,
    er.confidence::float AS chain_confidence
  FROM entity_relationships er
  JOIN served_routes sr ON sr.route_id = er.object_entity_id
  WHERE er.relationship_type = 'SERVED_BY_ROUTE'
    AND er.subject_entity_id != %s
)
SELECT
  ge.id::text,
  ge.entity_type,
  ge.subtype,
  ge.name,
  ge.source_name,
  ge.confidence::float,
  ge.source_tags,
  cp.via_route_id::text,
  cp.chain_confidence,
  rt.name  AS via_route_name,
  rt.subtype AS via_route_subtype,
  ST_AsGeoJSON(ge.geometry)::json AS geometry
FROM corridor_peers cp
JOIN geo_entities ge ON ge.id = cp.peer_id
JOIN geo_entities rt ON rt.id = cp.via_route_id
WHERE ge.entity_type IN ('port', 'facility')
ORDER BY ge.entity_type, ge.name NULLS LAST
LIMIT %s
"""

_ROUTES_SQL = """
SELECT
  ge.id::text,
  ge.entity_type,
  ge.subtype,
  ge.name,
  ge.source_name,
  ge.confidence::float,
  ge.source_tags,
  er.confidence::float AS relationship_confidence,
  ST_AsGeoJSON(ge.geometry)::json AS geometry
FROM entity_relationships er
JOIN geo_entities ge ON ge.id = er.object_entity_id
WHERE er.subject_entity_id = %s
  AND er.relationship_type = 'SERVED_BY_ROUTE'
ORDER BY ge.name NULLS LAST
"""

_PORT_NEWARK_SQL = """
SELECT
  id::text,
  entity_type,
  subtype,
  name,
  source_name,
  confidence::float,
  source_tags,
  ST_AsGeoJSON(geometry)::json AS geometry
FROM geo_entities
WHERE entity_type = 'port'
  AND (
    name ILIKE '%%Port Newark%%'
    OR name ILIKE '%%Newark%%Container%%'
    OR name ILIKE '%%Newark%%'
  )
ORDER BY
  CASE
    WHEN name ILIKE '%%Port Newark%%' THEN 1
    WHEN name ILIKE '%%Newark%%Container%%' THEN 2
    ELSE 3
  END,
  confidence DESC
LIMIT 1
"""

_PORT_NEWARK_COLD_CHAIN_FACILITIES_SQL = """
WITH served_routes AS (
  SELECT object_entity_id AS route_id
  FROM entity_relationships
  WHERE subject_entity_id = %s
    AND relationship_type = 'SERVED_BY_ROUTE'
),
candidates AS (
  SELECT DISTINCT
    ge.id::text,
    ge.entity_type,
    ge.subtype,
    ge.name,
    ge.source_name,
    ge.confidence::float,
    ge.source_tags,
    er.object_entity_id::text AS via_route_id,
    rt.name AS via_route_name,
    rt.subtype AS via_route_subtype,
    er.confidence::float AS chain_confidence,
    CASE
      WHEN coalesce(ge.name, '') ILIKE ANY (ARRAY['%%cold%%', '%%refriger%%', '%%reefer%%', '%%food%%'])
        OR ge.source_tags::text ILIKE ANY (ARRAY['%%cold%%', '%%refriger%%', '%%reefer%%', '%%food%%'])
      THEN 'cold-chain keyword match'
      WHEN ge.subtype IN ('warehouse', 'storage_tank', 'logistics')
      THEN 'logistics/storage facility sharing a served route'
      ELSE 'facility sharing a served route'
    END AS evidence_label,
    ST_AsGeoJSON(ge.geometry)::json AS geometry
  FROM entity_relationships er
  JOIN served_routes sr ON sr.route_id = er.object_entity_id
  JOIN geo_entities ge ON ge.id = er.subject_entity_id
  JOIN geo_entities rt ON rt.id = er.object_entity_id
  WHERE er.relationship_type = 'SERVED_BY_ROUTE'
    AND ge.entity_type = 'facility'
    AND ge.id != %s
)
SELECT *
FROM candidates
ORDER BY
  CASE
    WHEN evidence_label = 'cold-chain keyword match' THEN 1
    WHEN subtype = 'warehouse' THEN 2
    WHEN subtype = 'logistics' THEN 3
    ELSE 4
  END,
  name NULLS LAST
LIMIT %s
"""

_PORT_NEWARK_VESSELS_SQL = """
SELECT
  id::text,
  entity_type,
  subtype,
  name,
  source_name,
  confidence::float,
  source_tags,
  ST_Distance(geometry::geography, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)::geography)::float AS distance_m,
  ST_AsGeoJSON(geometry)::json AS geometry
FROM geo_entities
WHERE entity_type = 'location'
  AND subtype = 'vessel'
  AND source_name = 'ais_vessels'
  AND ST_DWithin(geometry::geography, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)::geography, %s)
  AND coalesce(source_tags->>'ship_type', '') IN (
    'cargo', 'cargo_hazmat_a', 'cargo_hazmat_b', 'cargo_hazmat_c', 'cargo_hazmat_d',
    'tanker', 'tanker_hazmat_a', 'tanker_hazmat_b', 'tanker_hazmat_c', 'tanker_hazmat_d'
  )
ORDER BY distance_m ASC
LIMIT %s
"""


def chain_connected_rows(entity_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Raw rows for corridor-peer lookup. Importable by tools.py."""
    try:
        with get_connection() as conn:
            return conn.execute(_CONNECTED_SQL, (entity_id, entity_id, limit)).fetchall()
    except psycopg.OperationalError:
        return []


def _entity_feature(row: dict[str, Any] | None, extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    props: dict[str, Any] = {
        "entity_type": row.get("entity_type"),
        "subtype": row.get("subtype"),
        "name": row.get("name"),
        "source_name": row.get("source_name"),
        "confidence": row.get("confidence"),
    }
    for key in (
        "source_tags",
        "via_route_id",
        "via_route_name",
        "via_route_subtype",
        "chain_confidence",
        "evidence_label",
        "distance_m",
    ):
        if row.get(key) is not None:
            props[key] = row[key]
    if extra:
        props.update(extra)
    return {"type": "Feature", "id": row["id"], "properties": props, "geometry": row["geometry"]}


def refrigerated_food_port_newark_chain(radius_km: float = 8, limit: int = 10) -> dict[str, Any]:
    """Worked chain example: refrigerated food imports through Port Newark."""
    params = {"radius_km": radius_km, "limit": limit}
    try:
        with get_connection() as conn:
            port = conn.execute(_PORT_NEWARK_SQL).fetchone()
            if not port:
                return _port_newark_chain_response(params, None, [], [], [])

            routes = conn.execute(_ROUTES_SQL, (port["id"],)).fetchall()
            facilities = conn.execute(
                _PORT_NEWARK_COLD_CHAIN_FACILITIES_SQL,
                (port["id"], port["id"], limit),
            ).fetchall()
            port_geom = json.dumps(port["geometry"])
            vessels = conn.execute(
                _PORT_NEWARK_VESSELS_SQL,
                (port_geom, port_geom, radius_km * 1000, limit),
            ).fetchall()
    except (KeyError, TypeError, psycopg.OperationalError):
        return _port_newark_chain_response(params, None, [], [], [])

    return _port_newark_chain_response(params, port, routes, facilities, vessels)


def _port_newark_chain_response(
    params: dict[str, Any],
    port: dict[str, Any] | None,
    routes: list[dict[str, Any]],
    facilities: list[dict[str, Any]],
    vessels: list[dict[str, Any]],
) -> dict[str, Any]:
    route_features = [_entity_feature(r, {"role": "served_route"}) for r in routes]
    facility_features = [_entity_feature(r, {"role": "cold_chain_or_logistics_facility"}) for r in facilities]
    vessel_features = [_entity_feature(r, {"role": "observed_cargo_or_tanker_vessel"}) for r in vessels]
    route_features = [f for f in route_features if f is not None]
    facility_features = [f for f in facility_features if f is not None]
    vessel_features = [f for f in vessel_features if f is not None]
    port_feature = _entity_feature(port, {"role": "anchor_port"}) if port else None

    evidence_count = (1 if port_feature else 0) + len(route_features) + len(facility_features) + len(vessel_features)
    confidence = 0.72 if port_feature and route_features else 0.45
    if not vessel_features:
        confidence -= 0.08
    if not facility_features:
        confidence -= 0.08

    return {
        "slug": "refrigerated-food-imports-port-newark",
        "question": "How would refrigerated food imports move through Port Newark into the regional supply chain?",
        "commodity": "refrigerated food imports",
        "parameters": params,
        "answer": (
            "The current graph models this as refrigerated/cold-chain cargo arriving on observed "
            "cargo-capable vessels near Port Newark, transferring through the Port Newark anchor, "
            "then moving onto routes that also serve nearby warehouse, logistics, storage, or food/cold "
            "keyword facilities."
        ),
        "flow": [
            {"step": 1, "label": "Observed maritime approach", "evidence": "AIS cargo/tanker vessel positions near Port Newark"},
            {"step": 2, "label": "Port handoff", "evidence": "Port Newark/near-Newark port entity from geo_entities"},
            {"step": 3, "label": "Corridor movement", "evidence": "SERVED_BY_ROUTE edges from the derived chain network"},
            {"step": 4, "label": "Regional cold/logistics handling", "evidence": "Facility peers sharing the same served routes"},
        ],
        "anchor_port": port_feature,
        "routes": {"count": len(route_features), "type": "FeatureCollection", "features": route_features},
        "facilities": {"count": len(facility_features), "type": "FeatureCollection", "features": facility_features},
        "vessels": {"count": len(vessel_features), "type": "FeatureCollection", "features": vessel_features},
        "evidence_count": evidence_count,
        "confidence": round(max(confidence, 0.2), 2),
        "limitations": [
            "This is an evidence trace, not a bill-of-lading or shipment manifest.",
            "AIS records show vessel position/type/destination when available; they do not prove a vessel carried refrigerated food.",
            "Cold-chain facilities are inferred from names/tags and route adjacency unless explicit cold-storage metadata exists.",
            "EIA petroleum terminals are not part of this chain; the current EIA pipeline covers power plants, so jet-fuel terminal tracing needs a new EIA petroleum terminal source.",
        ],
    }


def chain_route_rows(entity_id: str) -> list[dict[str, Any]]:
    """Raw rows for routes serving this entity. Importable by tools.py."""
    try:
        with get_connection() as conn:
            return conn.execute(_ROUTES_SQL, (entity_id,)).fetchall()
    except psycopg.OperationalError:
        return []


def _peer_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = []
    for r in rows:
        props: dict[str, Any] = {
            "entity_type": r["entity_type"],
            "subtype": r.get("subtype"),
            "name": r.get("name"),
            "source_name": r.get("source_name"),
            "confidence": r.get("confidence"),
            "chain_confidence": r.get("chain_confidence"),
            "via_route_id": r.get("via_route_id"),
            "via_route_name": r.get("via_route_name"),
            "via_route_subtype": r.get("via_route_subtype"),
        }
        if r.get("source_tags"):
            props["source_tags"] = r["source_tags"]
        features.append({"type": "Feature", "id": r["id"], "properties": props, "geometry": r["geometry"]})
    return features


@chains_router.get("/connected")
def connected(
    entity_id: Annotated[str, Query(description="geo_entities.id UUID")],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Find ports and facilities sharing a transportation corridor with this entity."""
    rows = chain_connected_rows(entity_id, limit)
    n = len(rows)
    return {
        "entity_id": entity_id,
        "count": n,
        "type": "FeatureCollection",
        "features": _peer_features(rows),
        "explanation": f"{n} asset{'s' if n != 1 else ''} share a corridor with entity {entity_id}.",
    }


@chains_router.get("/routes")
def entity_routes(
    entity_id: Annotated[str, Query(description="geo_entities.id UUID")],
) -> dict:
    """Return route LineStrings directly serving this entity (within 500m)."""
    rows = chain_route_rows(entity_id)
    n = len(rows)
    features = [
        {
            "type": "Feature",
            "id": r["id"],
            "properties": {
                "entity_type": r["entity_type"],
                "subtype": r.get("subtype"),
                "name": r.get("name"),
                "source_name": r.get("source_name"),
                "confidence": r.get("confidence"),
                "relationship_confidence": r.get("relationship_confidence"),
                "source_tags": r.get("source_tags"),
            },
            "geometry": r["geometry"],
        }
        for r in rows
    ]
    return {
        "entity_id": entity_id,
        "count": n,
        "type": "FeatureCollection",
        "features": features,
        "explanation": f"{n} route{'s' if n != 1 else ''} serve entity {entity_id}.",
    }


@chains_router.get("/summary")
def chain_summary() -> dict:
    """Count of entity_relationships by type; distinct node and route counts."""
    try:
        with get_connection() as conn:
            by_type = conn.execute(
                """
                SELECT relationship_type, count(*)::int AS count
                FROM entity_relationships
                GROUP BY relationship_type
                ORDER BY relationship_type
                """
            ).fetchall()
            node_row = conn.execute(
                """
                SELECT count(DISTINCT subject_entity_id)::int AS node_count
                FROM entity_relationships WHERE relationship_type = 'SERVED_BY_ROUTE'
                """
            ).fetchone()
            route_row = conn.execute(
                """
                SELECT count(DISTINCT object_entity_id)::int AS route_count
                FROM entity_relationships WHERE relationship_type = 'SERVED_BY_ROUTE'
                """
            ).fetchone()
    except psycopg.OperationalError:
        by_type = []
        node_row = {"node_count": 0}
        route_row = {"route_count": 0}

    total = sum(r["count"] for r in by_type)
    return {
        "total_edges": total,
        "by_type": [{"relationship_type": r["relationship_type"], "count": r["count"]} for r in by_type],
        "node_count": node_row["node_count"] if node_row else 0,
        "route_count": route_row["route_count"] if route_row else 0,
    }


@chains_router.get("/examples/refrigerated-food-port-newark")
def refrigerated_food_port_newark(
    radius_km: Annotated[float, Query(ge=1, le=50)] = 8,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, Any]:
    """Concrete worked chain: refrigerated food imports through Port Newark."""
    return refrigerated_food_port_newark_chain(radius_km=radius_km, limit=limit)
