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
RAW_DIR = ROOT / "sources" / "usaspending" / "raw"
CONTRACT_PATH = ROOT / "sources" / "usaspending" / "contract.yml"

AWARDS_API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

# Logistics/freight NAICS prefixes — truck, water, air, rail transport + support + warehousing
NAICS_CODES = [
    "4811", "4812",  # air transportation
    "482",           # rail transportation
    "4831", "4832",  # deep sea, coastal/Great Lakes water transport
    "4841", "4842",  # general freight trucking, specialized trucking
    "4881", "4882", "4883", "4884", "4885",  # transport support
    "4931", "4932",  # warehousing and storage
]

AOI_STATES = ["NY", "NJ", "CT"]
PAGE_SIZE = 100
MAX_PAGES = 50  # 5000 awards max


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


def fetch_awards_page(page: int) -> dict[str, Any]:
    body = {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],  # procurement contracts
            "recipient_location_states": AOI_STATES,
            "naics_codes": NAICS_CODES,
            "time_period": [{"start_date": "2020-01-01", "end_date": "2026-12-31"}],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "recipient_id",
            "recipient_uei",
            "Place of Performance State Code",
            "Award Amount",
            "NAICS Code",
            "NAICS Description",
            "Awarding Agency",
            "Period of Performance Current End Date",
            "recipient_location",
        ],
        "page": page,
        "limit": PAGE_SIZE,
        "sort": "Award Amount",
        "order": "desc",
    }
    resp = requests.post(
        AWARDS_API,
        json=body,
        headers={
            "User-Agent": "open-supply-chain/0.1",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def normalize_awards(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for award in results:
        loc = award.get("recipient_location") or {}
        try:
            lat = float(loc.get("latitude") or "")
            lon = float(loc.get("longitude") or "")
        except (ValueError, TypeError):
            continue

        uei = award.get("recipient_uei") or ""
        award_id = award.get("Award ID") or award.get("generated_unique_award_id") or ""
        # Prefer UEI for dedup (one entity per company); fall back to award_id
        source_entity_id = uei if uei else award_id
        if not source_entity_id:
            continue

        name = award.get("Recipient Name") or f"USASpending Contractor {source_entity_id}"
        naics_code = str(award.get("NAICS Code") or "")
        naics_desc = award.get("NAICS Description") or ""

        try:
            award_amount = float(award.get("Award Amount") or 0)
        except (ValueError, TypeError):
            award_amount = None

        records.append({
            "entity_type": "facility",
            "subtype": "contractor",
            "name": name,
            "description": None,
            "geometry": mapping(Point(lon, lat)),
            "source_name": "usaspending",
            "source_entity_id": source_entity_id,
            "source_tags": {
                "uei": uei or None,
                "award_id": award_id,
                "naics_code": naics_code,
                "naics_description": naics_desc,
                "award_amount_usd": award_amount,
                "awarding_agency": award.get("Awarding Agency"),
                "performance_end_date": award.get("Period of Performance Current End Date"),
                "state": loc.get("state_code"),
                "city": loc.get("city_name"),
            },
            "confidence": 0.75,
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


def insert_raw_ingestion(conn: Any, source_id: str, all_results: list[dict[str, Any]]) -> None:
    conn.execute(
        """
        INSERT INTO raw_ingestions
          (source_id, source_name, ingestion_key, request, payload, payload_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (source_name, ingestion_key, payload_hash) DO NOTHING
        """,
        (
            source_id,
            "usaspending",
            "logistics_contractors_ny_nj_ct",
            json.dumps({"states": AOI_STATES, "naics": NAICS_CODES}),
            json.dumps(all_results),
            payload_hash(all_results),
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
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    all_results: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        print(f"Fetching USASpending page {page}...")
        try:
            data = fetch_awards_page(page)
        except requests.HTTPError as exc:
            print(f"  Warning: {exc} — stopping pagination")
            break

        results = data.get("results") or []
        all_results.extend(results)
        total = data.get("page_metadata", {}).get("total", 0)
        print(f"  Got {len(results)} awards (total available: {total})")

        if len(results) < PAGE_SIZE or page * PAGE_SIZE >= total:
            break

    raw_path = RAW_DIR / "logistics_contractors.json"
    raw_path.write_text(json.dumps(all_results, indent=2))
    print(f"Fetched {len(all_results)} award records total")

    # Dedup by source_entity_id — keep highest-value award per recipient
    by_entity: dict[str, dict[str, Any]] = {}
    for award in all_results:
        uei = award.get("recipient_uei") or ""
        award_id = award.get("Award ID") or award.get("generated_unique_award_id") or ""
        key = uei if uei else award_id
        if not key:
            continue
        existing = by_entity.get(key)
        if existing is None:
            by_entity[key] = award
        else:
            try:
                if float(award.get("Award Amount") or 0) > float(existing.get("Award Amount") or 0):
                    by_entity[key] = award
            except (ValueError, TypeError):
                pass

    records = normalize_awards(list(by_entity.values()))
    print(f"Normalized {len(records)} unique contractor locations")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        insert_raw_ingestion(conn, source_id, all_results)
        upsert_geo_entities(conn, source_id, records)
        conn.commit()
    print(f"Loaded {len(records)} contractor facility locations into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch federal logistics/freight contractor locations for NY/NJ/CT from USASpending."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
