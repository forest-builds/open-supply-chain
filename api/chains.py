from __future__ import annotations

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


def chain_connected_rows(entity_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Raw rows for corridor-peer lookup. Importable by tools.py."""
    try:
        with get_connection() as conn:
            return conn.execute(_CONNECTED_SQL, (entity_id, entity_id, limit)).fetchall()
    except psycopg.OperationalError:
        return []


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
