from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import requests
import yaml
from shapely.geometry import LineString, Point, Polygon, mapping, shape

from pipelines.db import db_connection
from sources.osm.overpass_queries import (
    osm_facilities_query,
    osm_ports_query,
    osm_routes_query,
    tri_state_supply_chain_query,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "sources" / "osm" / "source_contract.yml"
AOI_PATH = ROOT / "sources" / "osm" / "tri_state_aoi.geojson"
RAW_DIR = ROOT / "sources" / "osm" / "raw"
OSM_JOBS = {
    "nyc_harbor_ports": osm_ports_query,
    "nyc_harbor_facilities": osm_facilities_query,
    "nyc_harbor_routes": osm_routes_query,
}


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open() as file:
        return yaml.safe_load(file)


def fetch_overpass(query: str) -> dict[str, Any]:
    contract = load_contract()
    errors: list[str] = []
    for api_url in contract.get("api_urls", [contract["api_url"]]):
        try:
            response = requests.post(
                api_url,
                data={"data": query},
                headers={"User-Agent": "open-supply-chain/0.1 (local development)"},
                timeout=120,
            )
        except requests.RequestException as exc:
            errors.append(f"{api_url}: {exc}")
            continue

        if response.ok:
            return response.json()

        message = response.text[:1000].replace("\n", " ")
        errors.append(f"{api_url}: {response.status_code} {message}")

    raise RuntimeError("All Overpass endpoints failed:\n" + "\n".join(errors))


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def osm_source_entity_id(element: dict[str, Any]) -> str:
    return f"{element['type']}/{element['id']}"


_FREIGHT_WATERWAYS = {"river", "canal", "bay", "strait"}


def classify_osm_element(tags: dict[str, Any]) -> str | None:
    if tags.get("seamark:type") == "harbour" or "harbour" in tags:
        return "port"
    if tags.get("landuse") == "port" or tags.get("industrial") == "port":
        return "port"
    if tags.get("amenity") == "ferry_terminal":
        return "port"
    if (
        tags.get("industrial") == "warehouse"
        or tags.get("building") == "warehouse"
        or tags.get("man_made") == "storage_tank"
        or tags.get("landuse") == "industrial"
    ):
        return "facility"
    if tags.get("highway") in {"motorway", "trunk", "motorway_link", "trunk_link"}:
        return "route"
    if tags.get("railway") == "rail":
        return "route"
    if tags.get("waterway") in _FREIGHT_WATERWAYS:
        return "route"
    if tags.get("route") == "ferry":
        return "route"
    return None


def route_subtype(tags: dict[str, Any]) -> str | None:
    if tags.get("highway") in {"motorway", "trunk", "motorway_link", "trunk_link"}:
        return "highway"
    if tags.get("railway") == "rail":
        return "rail"
    if tags.get("waterway") in _FREIGHT_WATERWAYS:
        return "waterway"
    if tags.get("route") == "ferry":
        return "ferry"
    return None


def facility_subtype(tags: dict[str, Any]) -> str | None:
    if tags.get("industrial") == "warehouse" or tags.get("building") == "warehouse":
        return "warehouse"
    if tags.get("man_made") == "storage_tank":
        return "storage_tank"
    if tags.get("industrial") == "logistics":
        return "logistics"
    if tags.get("landuse") == "industrial":
        return "industrial_site"
    return None


def element_geometry(element: dict[str, Any]) -> dict[str, Any] | None:
    if "lon" in element and "lat" in element:
        return mapping(Point(element["lon"], element["lat"]))

    if center := element.get("center"):
        return mapping(Point(center["lon"], center["lat"]))

    coords = [(point["lon"], point["lat"]) for point in element.get("geometry", [])]
    if len(coords) < 2:
        return None

    if len(coords) >= 4 and coords[0] == coords[-1]:
        return mapping(Polygon(coords))

    return mapping(LineString(coords))


def normalize_elements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        entity_type = classify_osm_element(tags)
        geometry = element_geometry(element)
        if not entity_type or not geometry:
            continue

        name = tags.get("name") or tags.get("operator") or tags.get("ref")
        records.append(
            {
                "entity_type": entity_type,
                "subtype": (
                    facility_subtype(tags)
                    if entity_type == "facility"
                    else route_subtype(tags)
                    if entity_type == "route"
                    else None
                ),
                "name": name,
                "description": tags.get("description"),
                "geometry": geometry,
                "source_name": "openstreetmap",
                "source_entity_id": osm_source_entity_id(element),
                "source_tags": tags,
                "confidence": 0.7,
            }
        )
    return records


def load_aoi() -> dict[str, Any]:
    with AOI_PATH.open() as file:
        return json.load(file)["features"][0]


def upsert_source(conn, contract: dict[str, Any]) -> str:
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


def upsert_aoi(conn) -> None:
    feature = load_aoi()
    geometry = shape(feature["geometry"])
    if geometry.geom_type == "Polygon":
        geometry = geometry.buffer(0)

    conn.execute(
        """
        INSERT INTO areas_of_interest (id, name, description, geometry, metadata)
        VALUES (%s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s::jsonb)
        ON CONFLICT (id) DO UPDATE SET
          name = EXCLUDED.name,
          description = EXCLUDED.description,
          geometry = EXCLUDED.geometry,
          metadata = EXCLUDED.metadata
        """,
        (
            feature["properties"]["id"],
            feature["properties"]["name"],
            feature["properties"].get("description"),
            json.dumps(mapping(geometry)),
            json.dumps(feature["properties"]),
        ),
    )


def insert_raw_ingestion(
    conn,
    source_id: str,
    ingestion_key: str,
    request_payload: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO raw_ingestions
          (source_id, source_name, ingestion_key, request, payload, payload_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (source_name, ingestion_key, payload_hash) DO NOTHING
        """,
        (
            source_id,
            "openstreetmap",
            ingestion_key,
            json.dumps(request_payload),
            json.dumps(payload),
            payload_hash(payload),
        ),
    )


def upsert_geo_entities(conn, source_id: str, records: list[dict[str, Any]]) -> None:
    for record in records:
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
                record["entity_type"],
                record["subtype"],
                record["name"],
                record["description"],
                json.dumps(record["geometry"]),
                source_id,
                record["source_name"],
                record["source_entity_id"],
                json.dumps(record["source_tags"]),
                record["confidence"],
            ),
        )


def save_raw_file(payload: dict[str, Any], ingestion_key: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{ingestion_key}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def run(
    ingestion_key: str,
    job: str | None,
    from_file: Path | None,
    dry_run: bool,
    include_facilities: bool,
    include_routes: bool,
) -> None:
    if job:
        query = OSM_JOBS[job]()
        ingestion_key = ingestion_key or job
    else:
        query = tri_state_supply_chain_query(
            include_facilities=include_facilities,
            include_routes=include_routes,
        )
    payload = json.loads(from_file.read_text()) if from_file else fetch_overpass(query)
    records = normalize_elements(payload)

    raw_path = save_raw_file(payload, ingestion_key)
    print(f"Fetched {len(payload.get('elements', []))} OSM elements")
    print(f"Normalized {len(records)} canonical geo entities")
    print(f"Saved raw payload to {raw_path}")

    if dry_run:
        return

    contract = load_contract()
    with db_connection() as conn:
        source_id = upsert_source(conn, contract)
        upsert_aoi(conn)
        insert_raw_ingestion(conn, source_id, ingestion_key, {"query": query}, payload)
        upsert_geo_entities(conn, source_id, records)
        conn.commit()
    print("Loaded OSM data into PostGIS")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and normalize OSM tri-state supply-chain data."
    )
    parser.add_argument(
        "--job",
        choices=sorted(OSM_JOBS),
        help="Run a named OSM source job with its own auditable raw payload.",
    )
    parser.add_argument("--ingestion-key")
    parser.add_argument("--from-file", type=Path)
    parser.add_argument(
        "--include-facilities",
        action="store_true",
        help="Also fetch warehouses and storage tanks for the seed bbox.",
    )
    parser.add_argument(
        "--include-routes",
        action="store_true",
        help="Also fetch motorway/trunk, rail, and ferry routes for the seed bbox.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ingestion_key = args.ingestion_key or args.job or "tri_state_supply_chain"
    run(
        ingestion_key,
        args.job,
        args.from_file,
        args.dry_run,
        args.include_facilities,
        args.include_routes,
    )


if __name__ == "__main__":
    main()
