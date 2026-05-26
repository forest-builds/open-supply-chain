from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from shapely.geometry import Point, mapping

from pipelines.db import db_connection

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "sources" / "gdacs" / "raw"
CONTRACT_PATH = ROOT / "sources" / "gdacs" / "contract.yml"

GDACS_API = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP"

_EVENTTYPE_MAP: dict[str, str] = {
    "EQ": "earthquake_gdacs",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "VO": "volcano",
    "TS": "tsunami",
    "WF": "wildfire",
    "DR": "drought",
}

_SEVERITY_MAP: dict[str, str] = {
    "Red": "Extreme",
    "Orange": "Severe",
    "Green": "Minor",
}


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as f:
        return yaml.safe_load(f)


def fetch_events() -> dict[str, Any]:
    resp = requests.get(
        GDACS_API,
        params={"alertlevel": "", "eventtype": "EQ,TC,FL,VO,TS,WF,DR"},
        headers={
            "User-Agent": "open-supply-chain/0.1",
            "Accept": "application/json",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_dt(val: str | None) -> str | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def normalize_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    features = payload.get("features") or []
    for feature in features:
        props = feature.get("properties") or {}
        event_id = props.get("eventid")
        if not event_id:
            continue

        alert_level = props.get("alertlevel") or "Green"
        event_type_code = props.get("eventtype") or "EQ"
        event_name = props.get("eventname") or props.get("name") or event_type_code
        event_type = _EVENTTYPE_MAP.get(event_type_code, event_type_code.lower())
        severity = _SEVERITY_MAP.get(alert_level, "Minor")

        # Geometry: prefer polygon from properties, fall back to point
        geom = feature.get("geometry")
        if not geom:
            lat = props.get("lat")
            lon = props.get("lon")
            if lat is not None and lon is not None:
                geom = mapping(Point(float(lon), float(lat)))
            else:
                geom = None

        from_date = _parse_dt(props.get("fromdate"))
        to_date = _parse_dt(props.get("todate"))

        now_iso = datetime.now(timezone.utc).isoformat()
        urgency = "Past" if (to_date and to_date < now_iso) else "Immediate"

        country = props.get("country") or props.get("countryname") or ""
        records.append({
            "event_type": event_type,
            "severity": severity,
            "certainty": "Observed",
            "urgency": urgency,
            "headline": f"{event_type_code} - {event_name}",
            "description": props.get("description") or f"GDACS {event_type} event — {event_name}.",
            "instruction": None,
            "area_desc": country or event_name,
            "effective_at": from_date,
            "expires_at": to_date,
            "geometry": geom,
            "source_name": "gdacs",
            "source_event_id": str(event_id),
            "source_tags": {
                "eventid": event_id,
                "eventtype": event_type_code,
                "alertlevel": alert_level,
                "country": country,
                "episodeid": props.get("episodeid"),
                "glide": props.get("glide"),
                "severity_value": props.get("severity", {}).get("value") if isinstance(props.get("severity"), dict) else props.get("severitydata", {}).get("severity") if isinstance(props.get("severitydata"), dict) else None,
            },
            "confidence": 0.90,
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
            "gdacs",
            "global_disasters",
            json.dumps({"eventtype": "EQ,TC,FL,VO,TS,WF,DR"}),
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
              urgency = EXCLUDED.urgency,
              headline = EXCLUDED.headline,
              description = EXCLUDED.description,
              expires_at = EXCLUDED.expires_at,
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


def run(dry_run: bool = False) -> None:
    payload = fetch_events()
    records = normalize_events(payload)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / "global_disasters.json"
    raw_path.write_text(json.dumps(payload, indent=2))
    print(f"Fetched {len(payload.get('features', []))} GDACS disaster events")
    print(f"Normalized {len(records)} risk events")
    print(f"Saved raw payload to {raw_path}")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        insert_raw_ingestion(conn, source_id, payload)
        upsert_risk_events(conn, source_id, records)
        conn.commit()
    print(f"Loaded {len(records)} GDACS disaster events into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GDACS global disaster events.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
