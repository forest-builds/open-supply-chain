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
RAW_DIR = ROOT / "sources" / "eia" / "raw"
CONTRACT_PATH = ROOT / "sources" / "eia" / "contract.yml"

EIA_BASE = "https://api.eia.gov/v2/"
AOI_STATES = ["NY", "NJ", "CT"]


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


def fetch_generators(api_key: str, state: str) -> dict[str, Any]:
    resp = requests.get(
        f"{EIA_BASE}electricity/operating-generator-capacity/",
        params={
            "api_key": api_key,
            "frequency": "annual",
            "facets[stateid][]": state,
            "data[]": ["nameplate-capacity-mw", "latitude", "longitude"],
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": 5000,
            "offset": 0,
        },
        headers={"User-Agent": "open-supply-chain/0.1"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def normalize_generators(payload: dict[str, Any], state: str) -> list[dict[str, Any]]:
    records = []
    data = payload.get("response", {}).get("data") or []
    seen_plants: set[str] = set()

    for row in data:
        plant_code = str(row.get("plantCode") or row.get("plant-id") or "")
        if not plant_code or plant_code in seen_plants:
            continue
        seen_plants.add(plant_code)

        try:
            lat = float(row.get("latitude") or "")
            lon = float(row.get("longitude") or "")
        except (ValueError, TypeError):
            continue

        plant_name = row.get("plantName") or row.get("plant-name") or f"EIA Plant {plant_code}"
        fuel_type = row.get("energy_source_code") or row.get("energysourcecode") or ""
        capacity = row.get("nameplate-capacity-mw")
        try:
            capacity_mw = float(capacity) if capacity is not None else None
        except (ValueError, TypeError):
            capacity_mw = None

        records.append({
            "entity_type": "facility",
            "subtype": "power_plant",
            "name": plant_name,
            "description": None,
            "geometry": mapping(Point(lon, lat)),
            "source_name": "eia",
            "source_entity_id": plant_code,
            "source_tags": {
                "plant_code": plant_code,
                "state": state,
                "fuel_type": fuel_type,
                "nameplate_capacity_mw": capacity_mw,
                "generator_id": row.get("generatorId") or row.get("generator-id"),
                "period": row.get("period"),
                "balancing_authority": row.get("balancing_authority_code") or row.get("balancingauthoritycode"),
            },
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


def insert_raw_ingestion(conn: Any, source_id: str, state: str, payload: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO raw_ingestions
          (source_id, source_name, ingestion_key, request, payload, payload_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (source_name, ingestion_key, payload_hash) DO NOTHING
        """,
        (
            source_id,
            "eia",
            f"generators_{state.lower()}",
            json.dumps({"state": state}),
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
    api_key = os.environ.get("EIA_API_KEY")
    if not api_key:
        print("Warning: EIA_API_KEY environment variable not set — skipping EIA ingestion.")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_records: dict[str, dict[str, Any]] = {}
    state_payloads: dict[str, dict[str, Any]] = {}

    for state in AOI_STATES:
        print(f"Fetching EIA generators for {state}...")
        try:
            payload = fetch_generators(api_key, state)
        except requests.HTTPError as exc:
            print(f"  Warning: {exc} — skipping {state}")
            continue

        raw_path = RAW_DIR / f"generators_{state.lower()}.json"
        raw_path.write_text(json.dumps(payload, indent=2))
        state_payloads[state] = payload

        records = normalize_generators(payload, state)
        print(f"  {len(records)} unique plants from {state}")
        for r in records:
            all_records[r["source_entity_id"]] = r

    records_list = list(all_records.values())
    print(f"Total unique EIA facilities: {len(records_list)}")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        for state, payload in state_payloads.items():
            insert_raw_ingestion(conn, source_id, state, payload)
        upsert_geo_entities(conn, source_id, records_list)
        conn.commit()
    print(f"Loaded {len(records_list)} EIA power plant locations into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch EIA power plant locations for NY/NJ/CT. Requires EIA_API_KEY env var."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
