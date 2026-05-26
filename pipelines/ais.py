from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests
import yaml
from shapely.geometry import Point, mapping

from pipelines.db import db_connection

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "sources" / "ais" / "raw"
CONTRACT_PATH = ROOT / "sources" / "ais" / "contract.yml"

AISHUB_API = "http://data.aishub.net/ws.php"

# Tri-state bounding box (matches USGS quakes extent)
EXTENT = {
    "latmin": 38.9,
    "latmax": 42.2,
    "lonmin": -75.0,
    "lonmax": -71.5,
}

# AIS ship type codes → human-readable category
_SHIP_TYPE_MAP: dict[int, str] = {
    0: "unknown",
    1: "reserved",
    20: "WIG",
    21: "WIG_hazmat_a",
    22: "WIG_hazmat_b",
    23: "WIG_hazmat_c",
    24: "WIG_hazmat_d",
    29: "WIG",
    30: "fishing",
    31: "towing",
    32: "towing_large",
    33: "dredging",
    34: "diving",
    35: "military",
    36: "sailing",
    37: "pleasure",
    40: "high_speed",
    50: "pilot",
    51: "search_rescue",
    52: "tug",
    53: "port_tender",
    54: "anti_pollution",
    55: "law_enforcement",
    58: "medical",
    59: "noncombatant",
    60: "passenger",
    70: "cargo",
    71: "cargo_hazmat_a",
    72: "cargo_hazmat_b",
    73: "cargo_hazmat_c",
    74: "cargo_hazmat_d",
    80: "tanker",
    81: "tanker_hazmat_a",
    82: "tanker_hazmat_b",
    83: "tanker_hazmat_c",
    84: "tanker_hazmat_d",
    90: "other",
}


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


def fetch_vessels(api_key: str) -> list[dict[str, Any]]:
    resp = requests.get(
        AISHUB_API,
        params={
            "username": api_key,
            "format": "1",
            "output": "json",
            "compress": "0",
            **{k: str(v) for k, v in EXTENT.items()},
        },
        headers={"User-Agent": "open-supply-chain/0.1"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    # AISHub returns [metadata_dict, [vessel_list]] or just [vessel_list]
    if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
        return data[1]
    if isinstance(data, list) and data and isinstance(data[0], list):
        return data[0]
    return data if isinstance(data, list) else []


def normalize_vessels(raw_vessels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for v in raw_vessels:
        mmsi = v.get("MMSI")
        if not mmsi:
            continue

        try:
            lon = float(v.get("LONGITUDE") or v.get("LON") or "")
            lat = float(v.get("LATITUDE") or v.get("LAT") or "")
        except (ValueError, TypeError):
            continue

        # Filter out obviously invalid coordinates
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            continue

        name = (v.get("NAME") or v.get("SHIPNAME") or "").strip() or f"MMSI {mmsi}"
        ship_type_code = int(v.get("TYPE") or v.get("SHIPTYPE") or 0)
        ship_type = _SHIP_TYPE_MAP.get(ship_type_code, f"type_{ship_type_code}")

        try:
            speed = float(v.get("SPEED") or 0)
        except (ValueError, TypeError):
            speed = None

        try:
            heading = float(v.get("HEADING") or v.get("COURSE") or 0)
        except (ValueError, TypeError):
            heading = None

        records.append({
            "entity_type": "location",
            "subtype": "vessel",
            "name": name,
            "description": None,
            "geometry": mapping(Point(lon, lat)),
            "source_name": "ais_vessels",
            "source_entity_id": str(mmsi),
            "source_tags": {
                "mmsi": mmsi,
                "imo": v.get("IMO"),
                "callsign": v.get("CALLSIGN") or v.get("CALL_SIGN"),
                "ship_type_code": ship_type_code,
                "ship_type": ship_type,
                "speed_knots": speed,
                "heading_deg": heading,
                "destination": (v.get("DESTINATION") or "").strip() or None,
                "eta": v.get("ETA"),
                "draught": v.get("DRAUGHT"),
            },
            "confidence": 0.85,
        })
    return records


def payload_hash(data: Any) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
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


def insert_raw_ingestion(conn: Any, source_id: str, raw_vessels: list[dict[str, Any]]) -> None:
    conn.execute(
        """
        INSERT INTO raw_ingestions
          (source_id, source_name, ingestion_key, request, payload, payload_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (source_name, ingestion_key, payload_hash) DO NOTHING
        """,
        (
            source_id,
            "ais_vessels",
            "tri_state_vessels",
            json.dumps(EXTENT),
            json.dumps(raw_vessels),
            payload_hash(raw_vessels),
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
              name = EXCLUDED.name,
              geometry = EXCLUDED.geometry,
              source_tags = EXCLUDED.source_tags,
              confidence = EXCLUDED.confidence,
              last_seen_at = now()
            """,
            (
                r["entity_type"], r["subtype"], r["name"], r["description"],
                json.dumps(r["geometry"]),
                source_id, r["source_name"], r["source_entity_id"],
                json.dumps(r["source_tags"]), r["confidence"],
            ),
        )


def run(dry_run: bool = False) -> None:
    api_key = os.environ.get("AIS_API_KEY")
    if not api_key:
        print("Warning: AIS_API_KEY environment variable not set — skipping AIS ingestion.")
        return

    raw_vessels = fetch_vessels(api_key)
    records = normalize_vessels(raw_vessels)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / "tri_state_vessels.json"
    raw_path.write_text(json.dumps(raw_vessels, indent=2))
    print(f"Fetched {len(raw_vessels)} AIS vessel positions")
    print(f"Normalized {len(records)} vessel locations")
    print(f"Saved raw payload to {raw_path}")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        insert_raw_ingestion(conn, source_id, raw_vessels)
        upsert_geo_entities(conn, source_id, records)
        conn.commit()
    print(f"Loaded {len(records)} AIS vessel positions into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch AIS vessel positions for the tri-state AOI. Requires AIS_API_KEY env var (AISHub username)."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
