import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Response
import psycopg

from api.db import get_connection
from pipelines.osm import normalize_elements

router = APIRouter()

EntityType = Literal["port", "facility", "route", "location", "aoi"]
ROOT = Path(__file__).resolve().parents[1]
OSM_RAW_PATH = ROOT / "sources" / "osm" / "raw" / "tri_state_supply_chain.json"
AOI_PATH = ROOT / "sources" / "osm" / "tri_state_aoi.geojson"


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def empty_feature_collection() -> dict:
    return feature_collection([])


def fallback_geo_features(entity_type: str | None = None, limit: int = 5000) -> list[dict]:
    if not OSM_RAW_PATH.exists():
        return []

    payload = json.loads(OSM_RAW_PATH.read_text())
    records = normalize_elements(payload)
    features = []
    for index, record in enumerate(records):
        if entity_type and record["entity_type"] != entity_type:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"fallback-{record['source_entity_id']}-{record['entity_type']}",
                "properties": {
                    "entity_type": record["entity_type"],
                    "subtype": record["subtype"],
                    "name": record["name"],
                    "description": record["description"],
                    "source_name": record["source_name"],
                    "source_entity_id": record["source_entity_id"],
                    "source_tags": record["source_tags"],
                    "confidence": record["confidence"],
                    "storage": "local_raw_fallback",
                },
                "geometry": record["geometry"],
            }
        )
        if len(features) >= limit:
            break
    return features


def fallback_aoi(aoi_id: str) -> dict:
    if not AOI_PATH.exists():
        return empty_feature_collection()

    payload = json.loads(AOI_PATH.read_text())
    for feature in payload.get("features", []):
        if feature.get("properties", {}).get("id") == aoi_id:
            return feature
    return empty_feature_collection()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@router.get("/aoi/{aoi_id}")
def get_aoi(aoi_id: str = "ny_nj_ct") -> dict:
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                  id,
                  name,
                  description,
                  ST_AsGeoJSON(geometry)::json AS geometry,
                  metadata
                FROM areas_of_interest
                WHERE id = %s
                """,
                (aoi_id,),
            ).fetchone()
    except psycopg.OperationalError:
        return fallback_aoi(aoi_id)

    if not row:
        return empty_feature_collection()

    return {
        "type": "Feature",
        "id": row["id"],
        "properties": {
            "name": row["name"],
            "description": row["description"],
            **row["metadata"],
        },
        "geometry": row["geometry"],
    }


@router.get("/geo/entities")
def list_geo_entities(
    entity_type: EntityType | None = None,
    subtype: str | None = None,
    limit: int = Query(default=5000, ge=1, le=25000),
) -> dict:
    where = []
    params: list[object] = []
    if entity_type:
        where.append("entity_type = %s")
        params.append(entity_type)
    if subtype:
        where.append("subtype = %s")
        params.append(subtype)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)

    try:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                  id::text,
              entity_type,
              subtype,
              name,
                  description,
                  source_name,
                  source_entity_id,
                  source_tags,
                  confidence::float,
                  ST_AsGeoJSON(geometry)::json AS geometry
                FROM geo_entities
                {where_sql}
                ORDER BY entity_type, name NULLS LAST
                LIMIT %s
                """,
                params,
            ).fetchall()
    except psycopg.OperationalError:
        return feature_collection(fallback_geo_features(entity_type, limit))

    return feature_collection(
        [
            {
                "type": "Feature",
                "id": row["id"],
                "properties": {
                    "entity_type": row["entity_type"],
                    "subtype": row["subtype"],
                    "name": row["name"],
                    "description": row["description"],
                    "source_name": row["source_name"],
                    "source_entity_id": row["source_entity_id"],
                    "source_tags": row["source_tags"],
                    "confidence": row["confidence"],
                },
                "geometry": row["geometry"],
            }
            for row in rows
        ]
    )


@router.get("/risk/events")
def list_risk_events(
    limit: int = Query(default=1000, ge=1, le=10000),
) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
              id::text,
              event_type,
              severity,
              certainty,
              urgency,
              headline,
              description,
              instruction,
              area_desc,
              effective_at,
              expires_at,
              source_name,
              source_event_id,
              source_tags,
              confidence::float,
              ST_AsGeoJSON(geometry)::json AS geometry
            FROM risk_events
            WHERE geometry IS NOT NULL
            ORDER BY
              CASE severity
                WHEN 'Extreme' THEN 1
                WHEN 'Severe' THEN 2
                WHEN 'Moderate' THEN 3
                WHEN 'Minor' THEN 4
                ELSE 5
              END,
              effective_at DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    return feature_collection(
        [
            {
                "type": "Feature",
                "id": row["id"],
                "properties": {
                    "record_type": "risk_event",
                    "event_type": row["event_type"],
                    "severity": row["severity"],
                    "certainty": row["certainty"],
                    "urgency": row["urgency"],
                    "headline": row["headline"],
                    "description": row["description"],
                    "instruction": row["instruction"],
                    "area_desc": row["area_desc"],
                    "effective_at": row["effective_at"].isoformat()
                    if row["effective_at"]
                    else None,
                    "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
                    "source_name": row["source_name"],
                    "source_event_id": row["source_event_id"],
                    "source_tags": row["source_tags"],
                    "confidence": row["confidence"],
                },
                "geometry": row["geometry"],
            }
            for row in rows
        ]
    )


@router.get("/risk/events/{event_id}/impacts")
def list_risk_event_impacts(
    event_id: str,
    entity_type: EntityType | None = None,
    limit: int = Query(default=5000, ge=1, le=25000),
) -> dict:
    where = ["ri.risk_event_id = %s"]
    params: list[object] = [event_id]
    if entity_type:
        where.append("ge.entity_type = %s")
        params.append(entity_type)
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
              ge.id::text,
              ge.entity_type,
              ge.subtype,
              ge.name,
              ge.description,
              ge.source_name,
              ge.source_entity_id,
              ge.source_tags,
              ge.confidence::float,
              ri.impact_method,
              ri.distance_m::float,
              ri.confidence::float AS impact_confidence,
              ri.evidence,
              ST_AsGeoJSON(ge.geometry)::json AS geometry
            FROM risk_impacts ri
            JOIN geo_entities ge ON ge.id = ri.impacted_entity_id
            WHERE {" AND ".join(where)}
            ORDER BY
              CASE ge.entity_type
                WHEN 'port' THEN 1
                WHEN 'facility' THEN 2
                WHEN 'route' THEN 3
                ELSE 4
              END,
              ri.impact_method,
              ri.distance_m NULLS FIRST,
              ge.name NULLS LAST
            LIMIT %s
            """,
            params,
        ).fetchall()

    return feature_collection(
        [
            {
                "type": "Feature",
                "id": row["id"],
                "properties": {
                    "entity_type": row["entity_type"],
                    "subtype": row["subtype"],
                    "name": row["name"],
                    "description": row["description"],
                    "source_name": row["source_name"],
                    "source_entity_id": row["source_entity_id"],
                    "source_tags": row["source_tags"],
                    "confidence": row["confidence"],
                    "impact_method": row["impact_method"],
                    "impact_distance_m": row["distance_m"],
                    "impact_confidence": row["impact_confidence"],
                    "impact_evidence": row["evidence"],
                },
                "geometry": row["geometry"],
            }
            for row in rows
        ]
    )


@router.get("/risk/impacts/summary")
def risk_impacts_summary() -> list[dict]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
              ge.entity_type,
              ri.impact_method,
              count(*)::int AS count
            FROM risk_impacts ri
            JOIN geo_entities ge ON ge.id = ri.impacted_entity_id
            GROUP BY ge.entity_type, ri.impact_method
            ORDER BY ge.entity_type, ri.impact_method
            """
        ).fetchall()


@router.get("/risk/scores")
def risk_scores(
    entity_type: EntityType | None = None,
    limit: int = Query(default=5000, ge=1, le=25000),
) -> dict:
    """Weighted risk score per geo_entity derived from active risk_impacts edges."""
    type_where = "AND ge.entity_type = %s" if entity_type else ""
    type_param: list[object] = [entity_type] if entity_type else []
    type_param.append(limit)
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
                  ST_AsGeoJSON(ge.geometry)::json AS geometry,
                  count(ri.id)::int AS impact_count,
                  sum(
                    CASE re.severity
                      WHEN 'Extreme'  THEN 4.0
                      WHEN 'Severe'   THEN 3.0
                      WHEN 'Moderate' THEN 2.0
                      WHEN 'Minor'    THEN 1.0
                      ELSE 0.5
                    END * ri.confidence::float
                  )::float AS risk_score,
                  (array_agg(re.severity ORDER BY
                    CASE re.severity
                      WHEN 'Extreme'  THEN 4
                      WHEN 'Severe'   THEN 3
                      WHEN 'Moderate' THEN 2
                      WHEN 'Minor'    THEN 1
                      ELSE 0
                    END DESC
                  ))[1] AS top_severity
                FROM geo_entities ge
                JOIN risk_impacts ri ON ri.impacted_entity_id = ge.id
                JOIN risk_events re ON re.id = ri.risk_event_id
                WHERE ge.entity_type IN ('port', 'facility', 'route')
                {type_where}
                GROUP BY ge.id, ge.entity_type, ge.subtype, ge.name, ge.source_name, ge.geometry
                ORDER BY risk_score DESC
                LIMIT %s
                """,
                type_param,
            ).fetchall()
    except psycopg.OperationalError:
        return feature_collection([])

    return feature_collection(
        [
            {
                "type": "Feature",
                "id": row["id"],
                "properties": {
                    "record_type": "risk_score",
                    "entity_type": row["entity_type"],
                    "subtype": row["subtype"],
                    "name": row["name"],
                    "source_name": row["source_name"],
                    "impact_count": row["impact_count"],
                    "risk_score": round(float(row["risk_score"]), 2),
                    "top_severity": row["top_severity"],
                },
                "geometry": row["geometry"],
            }
            for row in rows
        ]
    )


@router.get("/risk/summary")
def risk_summary() -> list[dict]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT severity, event_type, count(*)::int AS count
            FROM risk_events
            GROUP BY severity, event_type
            ORDER BY severity, event_type
            """
        ).fetchall()


@router.get("/geo/sources")
def geo_sources() -> list[dict]:
    try:
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT
                  s.name,
                  s.api_url,
                  s.attribution,
                  s.license,
                  s.refresh_rate,
                  count(ge.id)::int AS entity_count,
                  max(ge.last_seen_at) AS last_ingested_at
                FROM sources s
                LEFT JOIN geo_entities ge ON ge.source_id = s.id
                GROUP BY s.id, s.name, s.api_url, s.attribution, s.license, s.refresh_rate
                ORDER BY entity_count DESC NULLS LAST
                """
            ).fetchall()
    except psycopg.OperationalError:
        return []


@router.get("/geo/summary")
def geo_summary() -> list[dict]:
    try:
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT entity_type, count(*)::int AS count
                FROM geo_entities
                GROUP BY entity_type
                ORDER BY entity_type
                """
            ).fetchall()
    except psycopg.OperationalError:
        counts: dict[str, int] = {}
        for feature in fallback_geo_features():
            entity_type = str(feature["properties"]["entity_type"])
            counts[entity_type] = counts.get(entity_type, 0) + 1
        return [
            {"entity_type": entity_type, "count": count}
            for entity_type, count in sorted(counts.items())
        ]
