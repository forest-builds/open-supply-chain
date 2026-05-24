import json
import sys
from pathlib import Path

import pytest

import pipelines.osm as osm
from pipelines.osm import (
    OSM_JOBS,
    classify_osm_element,
    element_geometry,
    facility_subtype,
    fetch_overpass,
    insert_raw_ingestion,
    load_aoi,
    load_contract,
    normalize_elements,
    osm_source_entity_id,
    payload_hash,
    route_subtype,
    run,
    save_raw_file,
    upsert_aoi,
    upsert_geo_entities,
    upsert_source,
)
from sources.osm.overpass_queries import (
    osm_facilities_query,
    osm_ports_query,
    tri_state_supply_chain_query,
)


class FakeCursor:
    def __init__(self, row=None):
        self.row = row or {"id": "source-1"}

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return FakeCursor()

    def commit(self):
        self.committed = True


def test_classifies_ports_facilities_and_routes() -> None:
    assert classify_osm_element({"amenity": "ferry_terminal"}) == "port"
    assert classify_osm_element({"industrial": "port"}) == "port"
    assert classify_osm_element({"industrial": "warehouse"}) == "facility"
    assert classify_osm_element({"man_made": "storage_tank"}) == "facility"
    assert classify_osm_element({"railway": "rail"}) == "route"
    assert classify_osm_element({"highway": "trunk"}) == "route"
    assert classify_osm_element({"shop": "convenience"}) is None


def test_element_geometry_handles_points_lines_and_polygons() -> None:
    point = element_geometry({"type": "node", "id": 1, "lat": 40.7, "lon": -74.0})
    assert point == {"type": "Point", "coordinates": (-74.0, 40.7)}

    line = element_geometry(
        {
            "type": "way",
            "id": 2,
            "geometry": [
                {"lat": 40.0, "lon": -74.0},
                {"lat": 40.1, "lon": -74.1},
            ],
        }
    )
    assert line["type"] == "LineString"

    polygon = element_geometry(
        {
            "type": "way",
            "id": 3,
            "geometry": [
                {"lat": 40.0, "lon": -74.0},
                {"lat": 40.0, "lon": -73.9},
                {"lat": 40.1, "lon": -73.9},
                {"lat": 40.0, "lon": -74.0},
            ],
        }
    )
    assert polygon["type"] == "Polygon"


def test_normalize_elements_preserves_source_tags_and_ids() -> None:
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 42723103,
                "lat": 40.8521816,
                "lon": -73.7726765,
                "tags": {
                    "amenity": "ferry_terminal",
                    "name": "Hart Island Ferry Terminal",
                },
            },
            {
                "type": "node",
                "id": 999,
                "lat": 40.0,
                "lon": -74.0,
                "tags": {"shop": "convenience"},
            },
        ]
    }

    records = normalize_elements(payload)

    assert len(records) == 1
    assert records[0]["entity_type"] == "port"
    assert records[0]["subtype"] is None
    assert records[0]["name"] == "Hart Island Ferry Terminal"
    assert records[0]["source_name"] == "openstreetmap"
    assert records[0]["source_entity_id"] == "node/42723103"
    assert records[0]["source_tags"]["amenity"] == "ferry_terminal"


def test_query_keeps_heavy_layers_opt_in() -> None:
    base_query = tri_state_supply_chain_query()
    assert '"industrial"="warehouse"' not in base_query
    assert '"highway"~"motorway|trunk"' not in base_query

    expanded_query = tri_state_supply_chain_query(include_facilities=True, include_routes=True)
    assert '"industrial"="warehouse"' in expanded_query
    assert '"highway"~"motorway|trunk"' in expanded_query


def test_named_jobs_have_separate_source_queries() -> None:
    assert sorted(OSM_JOBS) == ["nyc_harbor_facilities", "nyc_harbor_ports", "nyc_harbor_routes"]
    assert '"amenity"="ferry_terminal"' in osm_ports_query()
    assert '"industrial"="warehouse"' in osm_facilities_query()
    assert '"amenity"="ferry_terminal"' not in osm_facilities_query()


def test_facility_normalization_derives_subtype() -> None:
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 123,
                "lat": 40.7,
                "lon": -74.0,
                "tags": {"industrial": "warehouse", "name": "Open Data Warehouse"},
            },
            {
                "type": "node",
                "id": 124,
                "lat": 40.8,
                "lon": -74.1,
                "tags": {"man_made": "storage_tank", "operator": "Tank Operator"},
            },
        ]
    }

    records = normalize_elements(payload)

    assert [record["entity_type"] for record in records] == ["facility", "facility"]
    assert [record["subtype"] for record in records] == ["warehouse", "storage_tank"]


def test_route_and_facility_subtype_helpers_cover_all_branches() -> None:
    assert route_subtype({"highway": "motorway"}) == "highway"
    assert route_subtype({"railway": "rail"}) == "rail"
    assert route_subtype({"waterway": "river"}) == "waterway"
    assert route_subtype({"route": "ferry"}) == "ferry"
    assert route_subtype({}) is None

    assert facility_subtype({"building": "warehouse"}) == "warehouse"
    assert facility_subtype({"industrial": "logistics"}) == "logistics"
    assert facility_subtype({"landuse": "industrial"}) == "industrial_site"
    assert facility_subtype({}) is None


def test_element_geometry_handles_center_and_invalid_way() -> None:
    assert (
        element_geometry({"type": "way", "id": 1, "center": {"lon": -74.0, "lat": 40.7}})["type"]
        == "Point"
    )
    assert (
        element_geometry({"type": "way", "id": 2, "geometry": [{"lon": -74.0, "lat": 40.7}]})
        is None
    )


def test_payload_hash_and_source_entity_id_are_stable() -> None:
    assert payload_hash({"b": 2, "a": 1}) == payload_hash({"a": 1, "b": 2})
    assert osm_source_entity_id({"type": "node", "id": 123}) == "node/123"


def test_load_contract_and_aoi(monkeypatch, tmp_path: Path) -> None:
    contract_path = tmp_path / "source.yml"
    aoi_path = tmp_path / "aoi.geojson"
    contract_path.write_text("source_name: openstreetmap\n")
    aoi_path.write_text(
        json.dumps(
            {
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": "ny_nj_ct", "name": "AOI"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-75, 39], [-71, 39], [-71, 42], [-75, 39]]],
                        },
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(osm, "CONTRACT_PATH", contract_path)
    monkeypatch.setattr(osm, "AOI_PATH", aoi_path)

    assert load_contract()["source_name"] == "openstreetmap"
    assert load_aoi()["properties"]["id"] == "ny_nj_ct"


def test_fetch_overpass_tries_fallback_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        osm,
        "load_contract",
        lambda: {
            "api_url": "https://bad.test",
            "api_urls": ["https://bad.test", "https://ok.test"],
        },
    )

    class FakeResponse:
        def __init__(self, ok, status_code=200, text="", payload=None):
            self.ok = ok
            self.status_code = status_code
            self.text = text
            self.payload = payload or {"elements": []}

        def json(self):
            return self.payload

    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return FakeResponse(False, 500, "bad") if len(calls) == 1 else FakeResponse(True)

    monkeypatch.setattr(osm.requests, "post", fake_post)

    assert fetch_overpass("[out:json];") == {"elements": []}
    assert calls == ["https://bad.test", "https://ok.test"]


def test_fetch_overpass_raises_after_all_fail(monkeypatch) -> None:
    monkeypatch.setattr(osm, "load_contract", lambda: {"api_url": "https://bad.test"})

    class FakeResponse:
        ok = False
        status_code = 429
        text = "too many requests"

    monkeypatch.setattr(osm.requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(RuntimeError, match="All Overpass endpoints failed"):
        fetch_overpass("[out:json];")


def test_db_helpers_execute_expected_statements(monkeypatch, tmp_path: Path) -> None:
    conn = FakeConnection()
    aoi_path = tmp_path / "aoi.geojson"
    aoi_path.write_text(
        json.dumps(
            {
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": "aoi", "name": "AOI"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-75, 39], [-71, 39], [-71, 42], [-75, 39]]],
                        },
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(osm, "AOI_PATH", aoi_path)
    record = normalize_elements(
        {
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 40.7,
                    "lon": -74.0,
                    "tags": {"amenity": "ferry_terminal"},
                }
            ]
        }
    )[0]

    source_id = upsert_source(
        conn,
        {
            "source_name": "openstreetmap",
            "api_url": "https://overpass.test",
            "auth_required": False,
            "refresh_rate": "weekly",
        },
    )
    upsert_aoi(conn)
    insert_raw_ingestion(conn, source_id, "key", {"query": "q"}, {"elements": []})
    upsert_geo_entities(conn, source_id, [record])

    assert source_id == "source-1"
    assert len(conn.calls) == 4


def test_save_raw_file_and_run_dry_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(osm, "RAW_DIR", tmp_path)
    monkeypatch.setattr(osm, "fetch_overpass", lambda query: {"elements": []})

    path = save_raw_file({"elements": []}, "manual")
    run(
        ingestion_key="tri_state",
        job=None,
        from_file=None,
        dry_run=True,
        include_facilities=True,
        include_routes=True,
    )

    assert path.exists()
    assert (tmp_path / "tri_state.json").exists()


def test_run_loads_from_file_and_commits(monkeypatch, tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"elements": []}))
    conn = FakeConnection()
    monkeypatch.setattr(osm, "RAW_DIR", tmp_path)
    monkeypatch.setattr(osm, "load_contract", lambda: {"source_name": "openstreetmap"})
    monkeypatch.setattr(osm, "upsert_source", lambda conn, contract: "source-1")
    monkeypatch.setattr(osm, "upsert_aoi", lambda conn: conn.calls.append(("aoi", None)))
    monkeypatch.setattr(osm, "insert_raw_ingestion", lambda *args: conn.calls.append(("raw", args)))
    monkeypatch.setattr(osm, "upsert_geo_entities", lambda *args: conn.calls.append(("geo", args)))
    monkeypatch.setattr(osm, "db_connection", lambda: conn)

    run(
        ingestion_key="key",
        job="nyc_harbor_ports",
        from_file=payload_path,
        dry_run=False,
        include_facilities=False,
        include_routes=False,
    )

    assert conn.committed


def test_osm_main_dispatches_run(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sys, "argv", ["osm", "--job", "nyc_harbor_ports", "--dry-run"])
    monkeypatch.setattr(osm, "run", lambda *args: calls.append(args))

    osm.main()

    assert calls == [("nyc_harbor_ports", "nyc_harbor_ports", None, True, False, False)]
