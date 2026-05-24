from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from pipelines.db import db_connection

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "sources" / "usgs" / "raw"
CONTRACT_PATH = ROOT / "sources" / "usgs" / "quakes_contract.yml"

USGS_BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Tri-state bounding box with small buffer
EXTENT = {
    "minlatitude": 38.9,
    "maxlatitude": 42.2,
    "minlongitude": -75.0,
    "maxlongitude": -71.5,
}

DEFAULT_DAYS = 30
DEFAULT_MIN_MAG = 1.0


def _severity(mag: float) -> str:
    if mag >= 6.0:
        return "Extreme"
    if mag >= 4.5:
        return "Severe"
    if mag >= 3.0:
        return "Moderate"
    return "Minor"


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


def fetch_earthquakes(days: int = DEFAULT_DAYS, min_magnitude: float = DEFAULT_MIN_MAG) -> dict[str, Any]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    resp = requests.get(
        USGS_BASE,
        params={
            "format": "geojson",
            "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "endtime": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "minmagnitude": min_magnitude,
            "orderby": "time",
            **EXTENT,
        },
        headers={"User-Agent": "open-supply-chain/0.1"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def normalize_earthquakes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        event_id = feature.get("id")
        mag = props.get("mag")
        if not event_id or mag is None:
            continue

        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue

        # Store as 2D point — depth lives in source_tags
        point_2d = {"type": "Point", "coordinates": [coords[0], coords[1]]}
        depth_km = coords[2] if len(coords) > 2 else None

        ts_ms = props.get("time")
        effective_at = (
            datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
            if ts_ms
            else None
        )

        mag_f = float(mag)
        place = props.get("place") or "Unknown location"
        mag_type = props.get("magType") or "M"

        records.append({
            "event_type": "earthquake",
            "severity": _severity(mag_f),
            "certainty": "Observed",
            "urgency": "Past",
            "headline": f"M{mag_f:.1f} - {place}",
            "description": (
                f"Magnitude {mag_f:.1f} {mag_type} earthquake"
                + (f" at depth {depth_km:.1f}km" if depth_km is not None else "")
                + f". {place}."
            ),
            "instruction": None,
            "area_desc": place,
            "effective_at": effective_at,
            "expires_at": None,
            "geometry": point_2d,
            "source_name": "usgs_earthquakes",
            "source_event_id": event_id,
            "source_tags": {**props, "depth_km": depth_km},
            "confidence": 0.95,
        })
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


def insert_raw_ingestion(conn: Any, source_id: str, payload: dict[str, Any], days: int, min_mag: float) -> None:
    conn.execute(
        """
        INSERT INTO raw_ingestions
          (source_id, source_name, ingestion_key, request, payload, payload_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (source_name, ingestion_key, payload_hash) DO NOTHING
        """,
        (
            source_id,
            "usgs_earthquakes",
            "tri_state_earthquakes",
            json.dumps({"extent": EXTENT, "days": days, "min_magnitude": min_mag}),
            json.dumps(payload),
            payload_hash(payload),
        ),
    )


def upsert_risk_events(conn: Any, source_id: str, records: list[dict[str, Any]]) -> None:
    for r in records:
        geometry_json = json.dumps(r["geometry"]) if r.get("geometry") else None
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
              severity = EXCLUDED.severity,
              headline = EXCLUDED.headline,
              description = EXCLUDED.description,
              source_tags = EXCLUDED.source_tags,
              last_seen_at = now()
            """,
            (
                r["event_type"], r["severity"], r["certainty"], r["urgency"],
                r["headline"], r["description"], r["instruction"],
                r["area_desc"], r["effective_at"], r["expires_at"],
                geometry_json, geometry_json,
                source_id, r["source_name"], r["source_event_id"],
                json.dumps(r["source_tags"]), r["confidence"],
            ),
        )


def run(dry_run: bool = False, days: int = DEFAULT_DAYS, min_magnitude: float = DEFAULT_MIN_MAG) -> None:
    payload = fetch_earthquakes(days=days, min_magnitude=min_magnitude)
    records = normalize_earthquakes(payload)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / "tri_state_earthquakes.json"
    raw_path.write_text(json.dumps(payload, indent=2))
    print(f"Fetched {len(payload.get('features', []))} USGS earthquake events (M{min_magnitude}+, last {days}d)")
    print(f"Normalized {len(records)} risk events")
    print(f"Saved raw payload to {raw_path}")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        insert_raw_ingestion(conn, source_id, payload, days, min_magnitude)
        upsert_risk_events(conn, source_id, records)
        conn.commit()
    print(f"Loaded {len(records)} earthquake risk events into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch USGS earthquake events for the tri-state AOI.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Lookback window in days (default 30)")
    parser.add_argument("--min-magnitude", type=float, default=DEFAULT_MIN_MAG, help="Min magnitude (default 1.0)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, days=args.days, min_magnitude=args.min_magnitude)


if __name__ == "__main__":
    main()
