import hashlib
import sys
from pathlib import Path

import pytest

import pipelines.osm_extracts as extracts
from pipelines.osm_extracts import (
    CanonicalExtractHandler,
    bbox_tuple,
    download_region,
    download_text,
    expected_md5,
    file_md5,
    in_bbox,
    list_regions,
    load_manifest,
    load_region,
    md5_path,
    parse_extract,
    region_path,
    stream_download,
    tags_dict,
    verify_md5,
)


def test_extract_manifest_declares_tri_state_regions() -> None:
    manifest = load_manifest()

    assert manifest["provider"] == "geofabrik"
    assert set(manifest["regions"]) == {"connecticut", "new_jersey", "new_york"}
    assert manifest["regions"]["new_jersey"]["url"].endswith("new-jersey-latest.osm.pbf")
    assert manifest["regions"]["new_york"]["md5_url"].endswith("new-york-latest.osm.pbf.md5")


def test_region_paths_are_local_extract_artifacts() -> None:
    path = region_path("new_jersey")

    assert path == Path("sources/osm/extracts/new_jersey.osm.pbf").resolve()


def test_md5_and_bbox_helpers() -> None:
    assert expected_md5("abc123  new-jersey-latest.osm.pbf") == "abc123"
    assert bbox_tuple("40.65,-74.20,40.72,-74.12") == (40.65, -74.20, 40.72, -74.12)
    assert bbox_tuple(None) is None
    assert in_bbox(-74.16, 40.70, (40.65, -74.20, 40.72, -74.12))
    assert in_bbox(-74.16, 40.70, None)
    assert not in_bbox(-73.90, 40.70, (40.65, -74.20, 40.72, -74.12))
    with pytest.raises(ValueError, match="bbox must be"):
        bbox_tuple("40,-74,41")


def test_verify_md5_rejects_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "extract.osm.pbf"
    path.write_bytes(b"open data")
    checksum = hashlib.md5(b"open data").hexdigest()

    verify_md5(path, f"{checksum}  extract.osm.pbf")
    with pytest.raises(RuntimeError, match="MD5 mismatch"):
        verify_md5(path, "badbadbad  extract.osm.pbf")


def test_file_md5_and_md5_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(extracts, "EXTRACT_DIR", tmp_path)
    path = tmp_path / "file.bin"
    path.write_bytes(b"abc")

    assert file_md5(path) == hashlib.md5(b"abc").hexdigest()
    assert md5_path("new_jersey") == tmp_path / "new_jersey.osm.pbf.md5"


def test_stream_download_writes_chunks(monkeypatch, tmp_path: Path) -> None:
    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int):
            yield b"abc"
            yield b"123"

    monkeypatch.setattr(extracts.requests, "get", lambda *args, **kwargs: FakeResponse())
    path = tmp_path / "download.osm.pbf"

    stream_download("https://example.test/download.osm.pbf", path)

    assert path.read_bytes() == b"abc123"


def test_stream_download_handles_completed_range(monkeypatch, tmp_path: Path) -> None:
    class FakeResponse:
        status_code = 416

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(extracts.requests, "get", lambda *args, **kwargs: FakeResponse())
    path = tmp_path / "download.osm.pbf"
    path.with_suffix(path.suffix + ".part").write_bytes(b"complete")

    stream_download("https://example.test/download.osm.pbf", path)

    assert path.read_bytes() == b"complete"


def test_download_text(monkeypatch) -> None:
    class FakeResponse:
        text = " checksum  file "

        def raise_for_status(self):
            return None

    monkeypatch.setattr(extracts.requests, "get", lambda *args, **kwargs: FakeResponse())

    assert download_text("https://example.test/md5") == "checksum  file"


def test_download_region_uses_manifest_and_verifies_checksum(monkeypatch, tmp_path: Path) -> None:
    payload = b"regional extract"
    checksum = hashlib.md5(payload).hexdigest()

    monkeypatch.setattr(extracts, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(
        extracts,
        "load_manifest",
        lambda: {
            "regions": {
                "tiny_region": {
                    "url": "https://example.test/tiny.osm.pbf",
                    "md5_url": "https://example.test/tiny.osm.pbf.md5",
                }
            }
        },
    )
    monkeypatch.setattr(extracts, "stream_download", lambda url, path: path.write_bytes(payload))
    monkeypatch.setattr(extracts, "download_text", lambda url: f"{checksum}  tiny.osm.pbf")

    path = download_region("tiny_region")

    assert path == tmp_path / "tiny_region.osm.pbf"
    assert path.read_bytes() == payload
    assert (tmp_path / "tiny_region.osm.pbf.md5").read_text().startswith(checksum)


def test_extract_handler_keeps_layer_filtered_records() -> None:
    handler = CanonicalExtractHandler(
        region_key="test_region",
        layers={"facility"},
        bbox=None,
        limit=1,
    )

    assert handler.should_keep("facility")
    handler.add_record(
        osm_type="node",
        osm_id=1,
        tags={"man_made": "storage_tank", "name": "Tank"},
        geometry={"type": "Point", "coordinates": [-74.0, 40.7]},
        entity_type="facility",
    )

    assert not handler.should_keep("facility")
    assert not handler.should_keep("port")
    assert handler.records[0]["source_entity_id"] == "test_region:node/1"
    assert handler.records[0]["subtype"] == "storage_tank"


def test_tags_dict_and_handler_node_way_branches() -> None:
    class Tag:
        def __init__(self, k, v):
            self.k = k
            self.v = v

    assert tags_dict([Tag("amenity", "ferry_terminal")]) == {"amenity": "ferry_terminal"}

    class Location:
        def __init__(self, lon, lat, valid=True):
            self.lon = lon
            self.lat = lat
            self._valid = valid

        def valid(self):
            return self._valid

    class Node:
        id = 1
        tags = [Tag("amenity", "ferry_terminal")]
        location = Location(-74.0, 40.7)

    class WayNode:
        def __init__(self, lon, lat, valid=True):
            self.location = Location(lon, lat, valid)

    class Way:
        id = 2
        tags = [Tag("building", "warehouse")]
        nodes = [
            WayNode(-74.0, 40.0),
            WayNode(-73.9, 40.0),
            WayNode(-73.9, 40.1),
            WayNode(-74.0, 40.0),
        ]

    handler = CanonicalExtractHandler("region", {"port", "facility"}, None, None)
    handler.node(Node())
    handler.way(Way())

    assert [record["entity_type"] for record in handler.records] == ["port", "facility"]
    assert handler.records[1]["geometry"]["type"] == "Polygon"

    class InvalidWay(Way):
        id = 3
        nodes = [WayNode(-74.0, 40.0, False)]

    handler.way(InvalidWay())
    assert len(handler.records) == 2


def test_parse_extract_requires_osmium(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(extracts, "osmium", None)

    with pytest.raises(RuntimeError, match="Install osmium"):
        parse_extract(tmp_path / "missing.osm.pbf", "region", {"port"}, None, None)


def test_load_region_requires_extract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(extracts, "EXTRACT_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="Missing"):
        load_region("missing", {"port"}, None, None)


def test_load_region_commits_records(monkeypatch, tmp_path: Path) -> None:
    class FakeConnection:
        def __init__(self):
            self.calls = []
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def commit(self):
            self.committed = True

    conn = FakeConnection()
    monkeypatch.setattr(extracts, "EXTRACT_DIR", tmp_path)
    (tmp_path / "tiny.osm.pbf").write_bytes(b"extract")
    (tmp_path / "tiny.osm.pbf.md5").write_text("abc123 tiny.osm.pbf\n")
    monkeypatch.setattr(extracts, "parse_extract", lambda *args: [{"entity_type": "port"}])
    monkeypatch.setattr(extracts, "load_contract", lambda: {"source_name": "openstreetmap"})
    monkeypatch.setattr(extracts, "upsert_source", lambda conn, contract: "source-1")
    monkeypatch.setattr(extracts, "upsert_aoi", lambda conn: conn.calls.append("aoi"))
    monkeypatch.setattr(extracts, "insert_raw_ingestion", lambda *args: conn.calls.append("raw"))
    monkeypatch.setattr(extracts, "upsert_geo_entities", lambda *args: conn.calls.append("geo"))
    monkeypatch.setattr(extracts, "db_connection", lambda: conn)

    load_region("tiny", {"port"}, None, 1)

    assert conn.committed
    assert conn.calls == ["aoi", "raw", "geo"]


def test_extracts_main_dispatches_download_and_load(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sys, "argv", ["osm_extracts", "download", "--region", "tiny"])
    monkeypatch.setattr(
        extracts,
        "download_region",
        lambda region: calls.append(("download", region)) or Path("tiny.osm.pbf"),
    )

    extracts.main()

    assert calls == [("download", "tiny")]

    calls.clear()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "osm_extracts",
            "load",
            "--region",
            "tiny",
            "--layer",
            "port",
            "--bbox",
            "40,-74,41,-73",
            "--limit",
            "5",
        ],
    )
    monkeypatch.setattr(extracts, "load_region", lambda *args: calls.append(args))

    extracts.main()

    assert calls == [("tiny", {"port"}, (40.0, -74.0, 41.0, -73.0), 5)]


def test_extracts_main_dispatches_list(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sys, "argv", ["osm_extracts", "list"])
    monkeypatch.setattr(extracts, "list_regions", lambda: calls.append("list"))

    extracts.main()

    assert calls == ["list"]


def test_list_regions_reports_download_status(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(extracts, "EXTRACT_DIR", tmp_path)
    monkeypatch.setattr(
        extracts,
        "load_manifest",
        lambda: {
            "regions": {
                "tiny_region": {
                    "url": "https://example.test/tiny.osm.pbf",
                }
            }
        },
    )

    list_regions()
    assert "tiny_region\tmissing" in capsys.readouterr().out

    (tmp_path / "tiny_region.osm.pbf").write_bytes(b"")
    list_regions()
    assert "tiny_region\tdownloaded" in capsys.readouterr().out
