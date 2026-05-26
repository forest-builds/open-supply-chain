from __future__ import annotations

import argparse
from typing import Any

from pipelines.db import db_connection
from pipelines.impact_network import ensure_source

SOURCE_NAME = "derived_chain_network"
SOURCE_API_URL = "postgres://geo_entities+routes"
DEFAULT_SERVED_BY_DISTANCE_M = 500
NODE_ENTITY_TYPES = ("port", "facility")


def _ensure_indexes(conn: Any) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS entity_relationships_object_idx
          ON entity_relationships (object_entity_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS entity_relationships_type_subject_idx
          ON entity_relationships (relationship_type, subject_entity_id)
        """
    )


def build_chain_network(
    conn: Any,
    source_id: str,
    distance_m: int = DEFAULT_SERVED_BY_DISTANCE_M,
) -> int:
    """Persist SERVED_BY_ROUTE edges linking ports/facilities to routes within distance_m."""
    bbox_deg = distance_m / 111_320
    conn.execute(
        """
        WITH node_route_pairs AS (
          SELECT
            node.id   AS node_entity_id,
            route.id  AS route_entity_id,
            jsonb_build_object(
              'rule',                 'node within 500m of route',
              'served_by_distance_m', %s,
              'node_type',            node.entity_type,
              'node_source',          node.source_name,
              'route_subtype',        route.subtype,
              'route_source',         route.source_name
            ) AS evidence
          FROM geo_entities node
          JOIN geo_entities route
            ON route.entity_type = 'route'
           AND node.entity_type  = ANY(%s)
           AND route.geometry && ST_Expand(node.geometry, %s)
           AND ST_DWithin(node.geometry::geography, route.geometry::geography, %s)
        )
        INSERT INTO entity_relationships
          (subject_entity_id, relationship_type, object_entity_id, source_id, confidence, evidence)
        SELECT
          node_entity_id,
          'SERVED_BY_ROUTE',
          route_entity_id,
          %s,
          0.750,
          evidence
        FROM node_route_pairs
        ON CONFLICT (subject_entity_id, relationship_type, object_entity_id, source_id)
        DO NOTHING
        """,
        (distance_m, list(NODE_ENTITY_TYPES), bbox_deg, distance_m, source_id),
    )
    row = conn.execute(
        """
        SELECT count(*)::int AS count FROM entity_relationships
        WHERE relationship_type = 'SERVED_BY_ROUTE' AND source_id = %s
        """,
        (source_id,),
    ).fetchone()
    return int(row["count"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SERVED_BY_ROUTE chain network edges.")
    parser.add_argument("--distance-m", type=int, default=DEFAULT_SERVED_BY_DISTANCE_M)
    args = parser.parse_args()

    with db_connection() as conn:
        _ensure_indexes(conn)
        source_id = ensure_source(
            conn,
            name=SOURCE_NAME,
            api_url=SOURCE_API_URL,
            auth_required=False,
            refresh_rate="after entity ingestion",
            metadata={
                "derived_from": ["geo_entities"],
                "rule": "ST_DWithin node within distance_m of route",
            },
        )
        count = build_chain_network(conn, source_id, distance_m=args.distance_m)
        conn.commit()

    print(f"Stored {count} SERVED_BY_ROUTE chain network edges")


if __name__ == "__main__":
    main()
