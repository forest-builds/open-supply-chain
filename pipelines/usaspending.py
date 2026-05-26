from __future__ import annotations

import argparse
import hashlib
import json
import time
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
NOMINATIM_API = "https://nominatim.openstreetmap.org/search"

# 4-digit logistics/freight NAICS codes only (API requires 2, 4, or 6 digits)
NAICS_CODES = [
    "4811", "4812",  # air transportation
    "4821", "4822",  # rail transportation
    "4831", "4832",  # water transportation (deep sea, coastal)
    "4841", "4842",  # truck transportation
    "4881", "4882", "4883", "4884", "4885",  # transport support activities
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
            "award_type_codes": ["A", "B", "C", "D"],
            "place_of_performance_locations": [
                {"country": "USA", "state": state} for state in AOI_STATES
            ],
            "naics_codes": NAICS_CODES,
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "NAICS Code",
            "NAICS Description",
            "Awarding Agency",
            "Period of Performance Current End Date",
            "Place of Performance City",
            "Place of Performance State Code",
            "Place of Performance Zip5",
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


# State centroid fallback (lat, lon) for when city is missing
_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "NY": (42.16, -74.99),
    "NJ": (40.22, -74.76),
    "CT": (41.60, -72.69),
}

_geocode_cache: dict[str, tuple[float, float] | None] = {}


def _geocode_city_state(city: str, state: str) -> tuple[float, float] | None:
    """Geocode city+state via Nominatim with in-process caching. Rate-limited to 1 req/sec."""
    key = f"{city.strip().upper()},{state.strip().upper()}"
    if key in _geocode_cache:
        return _geocode_cache[key]

    try:
        time.sleep(1.0)  # Nominatim rate limit: 1 req/sec
        resp = requests.get(
            NOMINATIM_API,
            params={
                "q": f"{city}, {state}, USA",
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            headers={"User-Agent": "open-supply-chain/0.1"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            coords: tuple[float, float] | None = (float(results[0]["lat"]), float(results[0]["lon"]))
        else:
            coords = None
    except Exception:
        coords = None

    _geocode_cache[key] = coords
    return coords


def normalize_awards(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for award in results:
        city = (award.get("Place of Performance City") or "").strip()
        state = (award.get("Place of Performance State Code") or "").strip()
        if not state:
            continue

        # Geocode if city available; otherwise use state centroid
        if city:
            coords = _geocode_city_state(city, state)
            confidence = 0.70
        else:
            coords = _STATE_CENTROIDS.get(state)
            confidence = 0.50  # state-level only

        if coords is None:
            continue
        lat, lon = coords

        award_id = award.get("Award ID") or award.get("generated_internal_id") or ""
        recipient_name = (award.get("Recipient Name") or "").strip()
        if not award_id or not recipient_name:
            continue

        try:
            award_amount = float(award.get("Award Amount") or 0)
        except (ValueError, TypeError):
            award_amount = None

        naics_code = str(award.get("NAICS Code") or "")

        records.append({
            "entity_type": "facility",
            "subtype": "contractor",
            "name": recipient_name,
            "description": None,
            "geometry": mapping(Point(lon, lat)),
            "source_name": "usaspending",
            "source_entity_id": award_id,
            "source_tags": {
                "award_id": award_id,
                "naics_code": naics_code,
                "naics_description": award.get("NAICS Description"),
                "award_amount_usd": award_amount,
                "awarding_agency": award.get("Awarding Agency"),
                "performance_end_date": award.get("Period of Performance Current End Date"),
                "city": city or None,
                "state": state,
            },
            "confidence": confidence,
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
        has_next = data.get("page_metadata", {}).get("hasNext", False)
        print(f"  Got {len(results)} awards (hasNext: {has_next})")

        if not results or len(results) < PAGE_SIZE or not has_next:
            break

    raw_path = RAW_DIR / "logistics_contractors.json"
    raw_path.write_text(json.dumps(all_results, indent=2))
    print(f"Fetched {len(all_results)} award records total")
    print("Geocoding unique city/state combos (1 req/sec via Nominatim)...")

    records = normalize_awards(all_results)
    print(f"Normalized {len(records)} contractor locations")

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
        description="Fetch federal logistics/freight contractor locations for NY/NJ/CT from USASpending.gov."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
