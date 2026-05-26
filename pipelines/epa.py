from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import requests
import yaml
from shapely.geometry import Point, mapping

from pipelines.db import db_connection

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "sources" / "epa" / "raw"
CONTRACT_PATH = ROOT / "sources" / "epa" / "contract.yml"

TRI_BASE = "https://data.epa.gov/efservice/TRI_FACILITY"
AOI_STATES = ["NY", "NJ", "CT"]
PAGE_SIZE = 5000


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


def _ddmmss_to_decimal(packed: int | str) -> float | None:
    """Convert DDMMSS packed integer (e.g. 403828 → 40.641°) to decimal degrees."""
    try:
        v = int(packed)
    except (ValueError, TypeError):
        return None
    if v == 0:
        return None
    degrees = v // 10000
    minutes = (v % 10000) // 100
    seconds = v % 100
    return degrees + minutes / 60 + seconds / 3600


def _parse_coordinates(record: dict[str, Any]) -> tuple[float, float] | None:
    """Return (lat, lon) in decimal WGS84, or None if unavailable."""
    # Prefer pref_latitude (decimal); longitude is stored as positive West → negate
    pref_lat = record.get("pref_latitude")
    pref_lon = record.get("pref_longitude")
    if pref_lat is not None and pref_lon is not None:
        try:
            lat = float(pref_lat)
            lon = -abs(float(pref_lon))  # stored as positive West degrees
            if lat != 0.0 and lon != 0.0:
                return lat, lon
        except (ValueError, TypeError):
            pass

    # Fall back to DDMMSS fac_latitude/fac_longitude
    lat = _ddmmss_to_decimal(record.get("fac_latitude"))
    lon_raw = _ddmmss_to_decimal(record.get("fac_longitude"))
    if lat is not None and lon_raw is not None:
        return lat, -lon_raw  # negate: stored as positive West
    return None


def fetch_facilities(state: str, start: int = 0) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{TRI_BASE}/STATE_ABBR/{state}/rows/{start}:{start + PAGE_SIZE - 1}/JSON",
        headers={"User-Agent": "open-supply-chain/0.1"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def normalize_facilities(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for r in raw:
        # Skip closed facilities
        closed = str(r.get("fac_closed_ind") or "").strip()
        if closed in ("1", "Y", "y"):
            continue

        coords = _parse_coordinates(r)
        if coords is None:
            continue
        lat, lon = coords

        fac_id = r.get("tri_facility_id") or ""
        if not fac_id:
            continue

        name = (r.get("facility_name") or "").strip() or f"TRI Facility {fac_id}"
        records.append({
            "entity_type": "facility",
            "subtype": "tri_facility",
            "name": name,
            "description": None,
            "geometry": mapping(Point(lon, lat)),
            "source_name": "epa_tri",
            "source_entity_id": fac_id,
            "source_tags": {
                "tri_facility_id": fac_id,
                "street_address": r.get("street_address"),
                "city_name": r.get("city_name"),
                "state_abbr": r.get("state_abbr"),
                "zip_code": r.get("zip_code"),
                "county_name": r.get("county_name"),
                "parent_company": r.get("parent_co_name") or r.get("standardized_parent_company"),
                "epa_registry_id": r.get("epa_registry_id"),
            },
            "confidence": 0.90,
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
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_records: dict[str, dict[str, Any]] = {}

    for state in AOI_STATES:
        print(f"Fetching EPA TRI facilities for {state}...")
        all_raw: list[dict[str, Any]] = []
        start = 0
        while True:
            try:
                batch = fetch_facilities(state, start)
            except requests.HTTPError as exc:
                print(f"  Warning: {exc} — stopping at offset {start}")
                break
            if not batch:
                break
            all_raw.extend(batch)
            print(f"  ...{len(all_raw)} fetched")
            if len(batch) < PAGE_SIZE:
                break
            start += PAGE_SIZE

        raw_path = RAW_DIR / f"tri_{state.lower()}.json"
        raw_path.write_text(json.dumps(all_raw, indent=2))

        records = normalize_facilities(all_raw)
        print(f"  {len(records)} active TRI facilities from {state}")
        for r in records:
            all_records[r["source_entity_id"]] = r

    records_list = list(all_records.values())
    print(f"Total unique EPA TRI facilities: {len(records_list)}")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        upsert_geo_entities(conn, source_id, records_list)
        conn.commit()
    print(f"Loaded {len(records_list)} EPA TRI facility locations into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch EPA Toxic Release Inventory (TRI) facility locations for NY/NJ/CT."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
