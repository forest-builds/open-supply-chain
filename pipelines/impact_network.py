from __future__ import annotations

import argparse
from typing import Any

from psycopg.types.json import Jsonb

from pipelines.db import db_connection

SOURCE_NAME = "derived_risk_impacts"
SOURCE_API_URL = "postgres://risk_events+geo_entities"
DEFAULT_NEAR_DISTANCE_M = 1000
CORE_ENTITY_TYPES = ("port", "facility", "route")


def ensure_source(
    conn: Any,
    name: str,
    api_url: str,
    auth_required: bool,
    refresh_rate: str,
    metadata: dict[str, Any],
) -> str:
    row = conn.execute(
        """
        INSERT INTO sources (name, api_url, auth_required, refresh_rate, metadata)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (name)
        DO UPDATE SET
          api_url = EXCLUDED.api_url,
          auth_required = EXCLUDED.auth_required,
          refresh_rate = EXCLUDED.refresh_rate,
          metadata = sources.metadata || EXCLUDED.metadata
        RETURNING id::text
        """,
        (name, api_url, auth_required, refresh_rate, Jsonb(metadata)),
    ).fetchone()
    return row["id"]


def rebuild_risk_impacts(
    conn: Any,
    source_id: str,
    near_distance_m: int = DEFAULT_NEAR_DISTANCE_M,
    entity_types: tuple[str, ...] = CORE_ENTITY_TYPES,
) -> int:
    """Persist risk_event -> geo_entity impact edges using deterministic PostGIS rules."""
    entity_type_filter = tuple(entity_types)
    near_distance_degrees = near_distance_m / 111_320
    conn.execute(
        """
        WITH candidate_impacts AS (
          SELECT
            re.id AS risk_event_id,
            ge.id AS impacted_entity_id,
            CASE
              WHEN ST_Intersects(ge.geometry, re.geometry) THEN 'intersects'
              ELSE 'near'
            END AS impact_method,
            CASE
              WHEN ST_Intersects(ge.geometry, re.geometry) THEN 0.0
              ELSE ST_Distance(ge.geometry, re.geometry) * 111320
            END AS distance_m,
            CASE
              WHEN ST_Intersects(ge.geometry, re.geometry) THEN 0.850
              ELSE 0.650
            END AS confidence,
            jsonb_build_object(
              'rule', 'risk_event intersects or is near core geo entity',
              'near_distance_m', %s,
              'risk_event_type', re.event_type,
              'risk_event_severity', re.severity,
              'risk_event_source', re.source_name,
              'entity_type', ge.entity_type,
              'entity_source', ge.source_name
            ) AS evidence
          FROM risk_events re
          JOIN geo_entities ge
            ON ge.entity_type = ANY(%s)
           AND re.geometry IS NOT NULL
           AND ge.geometry && ST_Expand(re.geometry, %s)
           AND (
             ST_Intersects(ge.geometry, re.geometry)
             OR ST_DWithin(ge.geometry, re.geometry, %s)
           )
        )
        INSERT INTO risk_impacts (
          risk_event_id,
          impacted_entity_id,
          relationship_type,
          impact_method,
          distance_m,
          source_id,
          confidence,
          evidence
        )
        SELECT
          risk_event_id,
          impacted_entity_id,
          'IMPACTS',
          impact_method,
          distance_m,
          %s,
          confidence,
          evidence
        FROM candidate_impacts
        ON CONFLICT (risk_event_id, impacted_entity_id, relationship_type)
        DO UPDATE SET
          impact_method = EXCLUDED.impact_method,
          distance_m = EXCLUDED.distance_m,
          source_id = EXCLUDED.source_id,
          confidence = EXCLUDED.confidence,
          evidence = EXCLUDED.evidence,
          last_seen_at = now()
        """,
        (
            near_distance_m,
            list(entity_type_filter),
            near_distance_degrees,
            near_distance_degrees,
            source_id,
        ),
    )
    row = conn.execute("SELECT count(*)::int AS count FROM risk_impacts").fetchone()
    return int(row["count"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build persisted risk impact edges.")
    parser.add_argument("--near-distance-m", type=int, default=DEFAULT_NEAR_DISTANCE_M)
    args = parser.parse_args()

    with db_connection() as conn:
        source_id = ensure_source(
            conn,
            name=SOURCE_NAME,
            api_url=SOURCE_API_URL,
            auth_required=False,
            refresh_rate="after risk/entity ingestion",
            metadata={
                "derived_from": ["risk_events", "geo_entities"],
                "rule": "ST_Intersects OR ST_DWithin",
            },
        )
        count = rebuild_risk_impacts(conn, source_id, near_distance_m=args.near_distance_m)
        conn.commit()

    print(f"Stored {count} risk impact edges")


if __name__ == "__main__":
    main()
