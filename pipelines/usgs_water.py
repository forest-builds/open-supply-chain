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
RAW_DIR = ROOT / "sources" / "usgs" / "raw"
CONTRACT_PATH = ROOT / "sources" / "usgs" / "water_contract.yml"

NWIS_SITE_URL = "https://waterservices.usgs.gov/nwis/site/"

AOI_STATES = ["NY", "NJ", "CT"]
# Stream, Estuary, Lake — all relevant to waterway and port risk
SITE_TYPES = "ST,ES,LK"


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


def fetch_sites(states: list[str] = AOI_STATES) -> str:
    """Fetch one state at a time and concatenate RDB bodies (NWIS rejects multi-state)."""
    combined_lines: list[str] = []
    header_written = False
    for state in states:
        resp = requests.get(
            NWIS_SITE_URL,
            params={
                "format": "rdb",
                "stateCd": state,
                "siteType": SITE_TYPES,
                "hasDataTypeCd": "iv",
                "siteStatus": "active",
            },
            headers={"User-Agent": "open-supply-chain/0.1"},
            timeout=60,
        )
        resp.raise_for_status()
        lines = resp.text.splitlines()
        comment_lines = [l for l in lines if l.startswith("#")]
        data_lines = [l for l in lines if not l.startswith("#") and l.strip()]
        if not data_lines:
            continue
        if not header_written:
            combined_lines.extend(comment_lines)
            combined_lines.extend(data_lines[:2])  # headers + format spec
            header_written = True
        combined_lines.extend(data_lines[2:])  # data rows only
    return "\n".join(combined_lines)


def parse_rdb(text: str) -> list[dict[str, str]]:
    """Parse USGS RDB (tab-delimited) format into list of dicts."""
    data_lines = [line for line in text.splitlines() if not line.startswith("#") and line.strip()]
    if len(data_lines) < 3:
        return []
    headers = data_lines[0].split("\t")
    # data_lines[1] is the format spec row (e.g. "5s\t15s\t...") — skip it
    records = []
    for line in data_lines[2:]:
        values = line.split("\t")
        records.append(dict(zip(headers, values)))
    return records


def normalize_sites(raw_records: list[dict[str, str]]) -> list[dict[str, Any]]:
    records = []
    for r in raw_records:
        try:
            lat = float(r.get("dec_lat_va", "").strip())
            lon = float(r.get("dec_long_va", "").strip())
        except (ValueError, AttributeError):
            continue

        site_no = r.get("site_no", "").strip()
        if not site_no:
            continue

        site_type = r.get("site_tp_cd", "ST").strip()
        site_type_labels = {"ST": "stream", "ES": "estuary", "LK": "lake", "WE": "wetland"}

        drain_area = r.get("drain_area_va", "").strip()
        records.append({
            "entity_type": "location",
            "subtype": "stream_gauge",
            "name": r.get("station_nm", "").strip() or None,
            "description": None,
            "geometry": mapping(Point(lon, lat)),
            "source_name": "usgs_water",
            "source_entity_id": site_no,
            "source_tags": {
                "site_no": site_no,
                "site_type": site_type,
                "site_type_label": site_type_labels.get(site_type, site_type),
                "huc_cd": r.get("huc_cd", "").strip() or None,
                "drain_area_sq_mi": float(drain_area) if drain_area else None,
                "agency_cd": r.get("agency_cd", "USGS").strip(),
            },
            "confidence": 0.95,
        })
    return records


def payload_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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
    raw_text = fetch_sites()
    raw_records = parse_rdb(raw_text)
    records = normalize_sites(raw_records)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / "tri_state_water_sites.rdb"
    raw_path.write_text(raw_text)
    print(f"Fetched {len(raw_records)} USGS water monitoring sites")
    print(f"Normalized {len(records)} location entities")
    print(f"Saved raw payload to {raw_path}")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        upsert_geo_entities(conn, source_id, records)
        conn.commit()
    print(f"Loaded {len(records)} USGS water gauge locations into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch USGS water monitoring sites for the tri-state AOI.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
