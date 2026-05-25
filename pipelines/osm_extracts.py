from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

import requests
import yaml
from shapely.geometry import LineString, Point, Polygon, mapping

from pipelines.db import db_connection
from pipelines.osm import (
    classify_osm_element,
    facility_subtype,
    insert_raw_ingestion,
    load_contract,
    route_subtype,
    upsert_aoi,
    upsert_geo_entities,
    upsert_source,
)

try:
    import osmium
except ImportError:  # pragma: no cover - exercised by environment, not logic
    osmium = None

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "sources" / "osm" / "extract_manifest.yml"
EXTRACT_DIR = ROOT / "sources" / "osm" / "extracts"


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open() as file:
        return yaml.safe_load(file)


def region_path(region_key: str) -> Path:
    return EXTRACT_DIR / f"{region_key}.osm.pbf"


def md5_path(region_key: str) -> Path:
    return EXTRACT_DIR / f"{region_key}.osm.pbf.md5"


def stream_download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    downloaded = tmp_path.stat().st_size if tmp_path.exists() else 0
    headers = {"User-Agent": "open-supply-chain/0.1", "Range": f"bytes={downloaded}-"}

    with requests.get(url, headers=headers, stream=True, timeout=60) as response:
        if response.status_code == 416:
            tmp_path.rename(path)
            return
        response.raise_for_status()
        mode = "ab" if response.status_code == 206 and downloaded else "wb"
        with tmp_path.open(mode) as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)

    tmp_path.rename(path)


def download_text(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": "open-supply-chain/0.1"}, timeout=30)
    response.raise_for_status()
    return response.text.strip()


def file_md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - file integrity check, not security.
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_md5(md5_text: str) -> str:
    return md5_text.split()[0]


def verify_md5(path: Path, md5_text: str) -> None:
    expected = expected_md5(md5_text)
    actual = file_md5(path)
    if actual != expected:
        raise RuntimeError(f"MD5 mismatch for {path}: expected {expected}, got {actual}")


def download_region(region_key: str) -> Path:
    manifest = load_manifest()
    region = manifest["regions"][region_key]
    extract_path = region_path(region_key)
    checksum_path = md5_path(region_key)

    stream_download(region["url"], extract_path)
    checksum_text = download_text(region["md5_url"])
    checksum_path.write_text(checksum_text + "\n")
    verify_md5(extract_path, checksum_text)
    return extract_path


def tags_dict(tags) -> dict[str, Any]:
    return {tag.k: tag.v for tag in tags}


def in_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float] | None) -> bool:
    if bbox is None:
        return True
    south, west, north, east = bbox
    return west <= lon <= east and south <= lat <= north


def bbox_tuple(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be south,west,north,east")
    return parts[0], parts[1], parts[2], parts[3]


class CanonicalExtractHandler(osmium.SimpleHandler):
    def __init__(
        self,
        region_key: str,
        layers: set[str],
        bbox: tuple[float, float, float, float] | None,
        limit: int | None,
    ) -> None:
        super().__init__()
        self.region_key = region_key
        self.layers = layers
        self.bbox = bbox
        self.limit = limit
        self.records: list[dict[str, Any]] = []

    def node(self, node) -> None:
        tags = tags_dict(node.tags)
        entity_type = classify_osm_element(tags)
        if not self.should_keep(entity_type):
            return
        if not in_bbox(node.location.lon, node.location.lat, self.bbox):
            return
        self.add_record(
            osm_type="node",
            osm_id=node.id,
            tags=tags,
            geometry=mapping(Point(node.location.lon, node.location.lat)),
            entity_type=entity_type,
        )

    def way(self, way) -> None:
        tags = tags_dict(way.tags)
        entity_type = classify_osm_element(tags)
        if not self.should_keep(entity_type):
            return

        coords = []
        for node in way.nodes:
            if not node.location.valid():
                return
            coords.append((node.location.lon, node.location.lat))
        if not coords or not any(in_bbox(lon, lat, self.bbox) for lon, lat in coords):
            return
        if len(coords) < 2:
            return

        geometry = (
            mapping(Polygon(coords))
            if len(coords) >= 4 and coords[0] == coords[-1]
            else mapping(LineString(coords))
        )
        self.add_record(
            osm_type="way",
            osm_id=way.id,
            tags=tags,
            geometry=geometry,
            entity_type=entity_type,
        )

    def should_keep(self, entity_type: str | None) -> bool:
        if entity_type is None:
            return False
        if entity_type not in self.layers:
            return False
        if self.limit is not None and len(self.records) >= self.limit:
            return False
        return True

    def add_record(
        self,
        osm_type: str,
        osm_id: int,
        tags: dict[str, Any],
        geometry: dict[str, Any],
        entity_type: str,
    ) -> None:
        self.records.append(
            {
                "entity_type": entity_type,
                "subtype": (
                    facility_subtype(tags)
                    if entity_type == "facility"
                    else route_subtype(tags)
                    if entity_type == "route"
                    else None
                ),
                "name": tags.get("name") or tags.get("operator") or tags.get("ref"),
                "description": tags.get("description"),
                "geometry": geometry,
                "source_name": "openstreetmap",
                "source_entity_id": f"{self.region_key}:{osm_type}/{osm_id}",
                "source_tags": tags,
                "confidence": 0.7,
            }
        )


def parse_extract(
    path: Path,
    region_key: str,
    layers: set[str],
    bbox: tuple[float, float, float, float] | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    if osmium is None:
        raise RuntimeError("Install osmium to parse .osm.pbf extracts: pip install -e '.[dev]'")
    handler = CanonicalExtractHandler(region_key, layers, bbox, limit)
    handler.apply_file(str(path), locations=True)
    return handler.records


def load_region(
    region_key: str,
    layers: set[str],
    bbox: tuple[float, float, float, float] | None,
    limit: int | None,
) -> None:
    extract_path = region_path(region_key)
    if not extract_path.exists():
        raise RuntimeError(f"Missing {extract_path}. Run download first.")

    records = parse_extract(extract_path, region_key, layers, bbox, limit)
    checksum_text = (
        md5_path(region_key).read_text().strip() if md5_path(region_key).exists() else ""
    )
    request_payload = {
        "provider": "geofabrik",
        "region": region_key,
        "layers": sorted(layers),
        "bbox": bbox,
        "limit": limit,
        "extract_path": str(extract_path),
    }
    payload = {
        "artifact_type": "osm.pbf",
        "region": region_key,
        "path": str(extract_path),
        "bytes": extract_path.stat().st_size,
        "md5": expected_md5(checksum_text) if checksum_text else None,
        "record_count": len(records),
    }
    layer_key = "_".join(sorted(layers))
    bbox_key = "all" if bbox is None else "_".join(str(value) for value in bbox)
    ingestion_key = f"geofabrik_{region_key}_{layer_key}_{bbox_key}"

    with db_connection() as conn:
        source_id = upsert_source(conn, load_contract())
        upsert_aoi(conn)
        insert_raw_ingestion(conn, source_id, ingestion_key, request_payload, payload)
        upsert_geo_entities(conn, source_id, records)
        conn.commit()
    print(f"Loaded {len(records)} canonical records from {extract_path}")


def list_regions() -> None:
    manifest = load_manifest()
    for key, region in manifest["regions"].items():
        status = "downloaded" if region_path(key).exists() else "missing"
        print(f"{key}\t{status}\t{region['url']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and load OSM regional extracts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")

    download_parser = subparsers.add_parser("download")
    download_parser.add_argument("--region", action="append", required=True)

    load_parser = subparsers.add_parser("load")
    load_parser.add_argument("--region", action="append", required=True)
    load_parser.add_argument(
        "--layer", action="append", choices=["port", "facility", "route"], required=True
    )
    load_parser.add_argument("--bbox", help="south,west,north,east filter applied while parsing")
    load_parser.add_argument("--limit", type=int)

    args = parser.parse_args()
    if args.command == "list":
        list_regions()
    elif args.command == "download":
        for region in args.region:
            path = download_region(region)
            print(f"Downloaded and verified {path}")
    elif args.command == "load":
        for region in args.region:
            load_region(region, set(args.layer), bbox_tuple(args.bbox), args.limit)


if __name__ == "__main__":
    main()
