from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests
import yaml
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

from pipelines.db import db_connection

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "sources" / "noaa" / "raw"
CONTRACT_PATH = ROOT / "sources" / "noaa" / "source_contract.yml"
ALERTS_CONTRACT_PATH = ROOT / "sources" / "noaa" / "alerts_contract.yml"

# Tri-state bounding box: minlat,minlon,maxlat,maxlon (NY + NJ + CT)
EXTENT = "38.9,-75.0,42.2,-71.5"


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


def load_alerts_contract() -> dict[str, Any]:
    with ALERTS_CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


CDO_BASE = "https://www.ncdc.noaa.gov/cdo-web/api/v2"
NWS_ALERTS_BASE = "https://api.weather.gov/alerts/active"
TRI_STATE_AREAS = ["NY", "NJ", "CT"]


def fetch_stations(token: str) -> list[dict[str, Any]]:
    # GHCND + datacoverage filter keeps only active quality stations — ~2 pages for tri-state
    results: list[dict[str, Any]] = []
    offset = 1
    while True:
        resp = requests.get(
            f"{CDO_BASE}/stations",
            headers={"token": token},
            params={
                "extent": EXTENT,
                "datasetid": "GHCND",
                "datacoverage": "0.5",
                "limit": 1000,
                "offset": offset,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("results", [])
        results.extend(batch)
        total = data["metadata"]["resultset"]["count"]
        print(f"  fetched {len(results)}/{total} stations...")
        if not batch or offset + len(batch) - 1 >= total:
            break
        offset += len(batch)
    return results


def fetch_active_alerts(areas: list[str] = TRI_STATE_AREAS) -> dict[str, Any]:
    features_by_id: dict[str, dict[str, Any]] = {}
    zone_geometry_cache: dict[str, dict[str, Any] | None] = {}
    for area in areas:
        resp = requests.get(
            NWS_ALERTS_BASE,
            headers={
                "User-Agent": "open-supply-chain/0.1",
                "Accept": "application/geo+json",
            },
            params={"area": area},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        for feature in data.get("features", []):
            feature_id = feature.get("id") or feature.get("properties", {}).get("id")
            if feature_id:
                if feature.get("geometry") is None:
                    feature["geometry"] = alert_zone_geometry(feature, zone_geometry_cache)
                features_by_id[feature_id] = feature

    return {"type": "FeatureCollection", "features": list(features_by_id.values())}


def fetch_zone_geometry(url: str) -> dict[str, Any] | None:
    resp = requests.get(
        url,
        headers={
            "User-Agent": "open-supply-chain/0.1",
            "Accept": "application/geo+json",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("geometry")


def alert_zone_geometry(
    feature: dict[str, Any],
    zone_geometry_cache: dict[str, dict[str, Any] | None],
) -> dict[str, Any] | None:
    geometries = []
    for url in feature.get("properties", {}).get("affectedZones", []):
        if url not in zone_geometry_cache:
            zone_geometry_cache[url] = fetch_zone_geometry(url)
        geometry = zone_geometry_cache[url]
        if geometry:
            geometries.append(shape(geometry))
    if not geometries:
        return None
    return mapping(unary_union(geometries))


def normalize_stations(stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for s in stations:
        lat, lon = s.get("latitude"), s.get("longitude")
        if lat is None or lon is None:
            continue
        records.append(
            {
                "entity_type": "location",
                "subtype": "weather_station",
                "name": s.get("name"),
                "description": None,
                "geometry": mapping(Point(lon, lat)),
                "source_name": "noaa_cdo",
                "source_entity_id": s["id"],
                "source_tags": {
                    "elevation": s.get("elevation"),
                    "mindate": s.get("mindate"),
                    "maxdate": s.get("maxdate"),
                    "datacoverage": s.get("datacoverage"),
                },
                "confidence": 0.95,
            }
        )
    return records


def normalize_alerts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        source_event_id = props.get("id") or feature.get("id")
        if not source_event_id:
            continue
        records.append(
            {
                "event_type": props.get("event") or "weather_alert",
                "severity": props.get("severity"),
                "certainty": props.get("certainty"),
                "urgency": props.get("urgency"),
                "headline": props.get("headline"),
                "description": props.get("description"),
                "instruction": props.get("instruction"),
                "area_desc": props.get("areaDesc"),
                "effective_at": props.get("effective"),
                "expires_at": props.get("expires"),
                "geometry": feature.get("geometry"),
                "source_name": "noaa_nws_alerts",
                "source_event_id": source_event_id,
                "source_tags": props,
                "confidence": 0.95,
            }
        )
    return records


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def upsert_source(conn: Any, contract: dict[str, Any]) -> str:
    row = conn.execute(
        """
        INSERT INTO sources (name, api_url, auth_required, refresh_rate, license, attribution, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (name) DO UPDATE SET
          api_url = EXCLUDED.api_url,
          auth_required = EXCLUDED.auth_required,
          refresh_rate = EXCLUDED.refresh_rate,
          license = EXCLUDED.license,
          attribution = EXCLUDED.attribution,
          metadata = EXCLUDED.metadata
        RETURNING id
        """,
        (
            contract["source_name"],
            contract["api_url"],
            contract["auth_required"],
            contract["refresh_rate"],
            contract.get("license"),
            contract.get("attribution"),
            json.dumps(contract),
        ),
    ).fetchone()
    return str(row["id"])


def insert_raw_ingestion(conn: Any, source_id: str, payload: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO raw_ingestions
          (source_id, source_name, ingestion_key, request, payload, payload_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (source_name, ingestion_key, payload_hash) DO NOTHING
        """,
        (
            source_id,
            "noaa_cdo",
            "tri_state_stations",
            json.dumps({"extent": EXTENT}),
            json.dumps(payload),
            payload_hash(payload),
        ),
    )


def insert_alerts_raw_ingestion(conn: Any, source_id: str, payload: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO raw_ingestions
          (source_id, source_name, ingestion_key, request, payload, payload_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (source_name, ingestion_key, payload_hash) DO NOTHING
        """,
        (
            source_id,
            "noaa_nws_alerts",
            "tri_state_active_alerts",
            json.dumps({"areas": TRI_STATE_AREAS, "api_url": NWS_ALERTS_BASE}),
            json.dumps(payload),
            payload_hash(payload),
        ),
    )


def upsert_geo_entities(conn: Any, source_id: str, records: list[dict[str, Any]]) -> None:
    for r in records:
        conn.execute(
            """
            INSERT INTO geo_entities
              (entity_type, subtype, name, description, geometry, source_id, source_name,
               source_entity_id, source_tags, confidence)
            VALUES
              (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (source_name, source_entity_id, entity_type) DO UPDATE SET
              subtype = EXCLUDED.subtype,
              name = EXCLUDED.name,
              description = EXCLUDED.description,
              geometry = EXCLUDED.geometry,
              source_tags = EXCLUDED.source_tags,
              confidence = EXCLUDED.confidence,
              last_seen_at = now()
            """,
            (
                r["entity_type"],
                r["subtype"],
                r["name"],
                r["description"],
                json.dumps(r["geometry"]),
                source_id,
                r["source_name"],
                r["source_entity_id"],
                json.dumps(r["source_tags"]),
                r["confidence"],
            ),
        )


def upsert_risk_events(conn: Any, source_id: str, records: list[dict[str, Any]]) -> None:
    for r in records:
        geometry_json = json.dumps(r["geometry"]) if r["geometry"] else None
        conn.execute(
            """
            INSERT INTO risk_events
              (event_type, severity, certainty, urgency, headline, description, instruction,
               area_desc, effective_at, expires_at, geometry, source_id, source_name,
               source_event_id, source_tags, confidence)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz,
               CASE WHEN %s::json IS NULL THEN NULL ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s::json), 4326) END,
               %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (source_name, source_event_id) DO UPDATE SET
              event_type = EXCLUDED.event_type,
              severity = EXCLUDED.severity,
              certainty = EXCLUDED.certainty,
              urgency = EXCLUDED.urgency,
              headline = EXCLUDED.headline,
              description = EXCLUDED.description,
              instruction = EXCLUDED.instruction,
              area_desc = EXCLUDED.area_desc,
              effective_at = EXCLUDED.effective_at,
              expires_at = EXCLUDED.expires_at,
              geometry = EXCLUDED.geometry,
              source_tags = EXCLUDED.source_tags,
              confidence = EXCLUDED.confidence,
              last_seen_at = now()
            """,
            (
                r["event_type"],
                r["severity"],
                r["certainty"],
                r["urgency"],
                r["headline"],
                r["description"],
                r["instruction"],
                r["area_desc"],
                r["effective_at"],
                r["expires_at"],
                geometry_json,
                geometry_json,
                source_id,
                r["source_name"],
                r["source_event_id"],
                json.dumps(r["source_tags"]),
                r["confidence"],
            ),
        )


def run(dry_run: bool) -> None:
    token = os.environ.get("NOAA_CDO_TOKEN")
    if not token:
        raise RuntimeError("NOAA_CDO_TOKEN environment variable is required")
    stations = fetch_stations(token)
    records = normalize_stations(stations)

    payload = {"stations": stations}
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / "tri_state_stations.json"
    raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Fetched {len(stations)} NOAA CDO weather stations")
    print(f"Normalized {len(records)} location entities")
    print(f"Saved raw payload to {raw_path}")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        insert_raw_ingestion(conn, source_id, payload)
        upsert_geo_entities(conn, source_id, records)
        conn.commit()
    print("Loaded NOAA weather stations into PostGIS")


def run_alerts(dry_run: bool) -> None:
    payload = fetch_active_alerts()
    records = normalize_alerts(payload)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / "tri_state_active_alerts.json"
    raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Fetched {len(payload.get('features', []))} active NWS alerts")
    print(f"Normalized {len(records)} risk events")
    print(f"Saved raw payload to {raw_path}")

    if dry_run:
        return

    contract = load_alerts_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        insert_alerts_raw_ingestion(conn, source_id, payload)
        upsert_risk_events(conn, source_id, records)
        conn.commit()
    print("Loaded NOAA active alerts into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch NOAA datasets for the tri-state AOI.")
    parser.add_argument(
        "--dataset",
        choices=["stations", "alerts"],
        default="stations",
        help="NOAA dataset to fetch.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dataset == "stations":
        run(args.dry_run)
    else:
        run_alerts(args.dry_run)


if __name__ == "__main__":
    main()
