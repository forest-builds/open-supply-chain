import json
import sys
from pathlib import Path

import pytest

import pipelines.usgs_quakes as quakes
import pipelines.usgs_water as water


class FakeConnection:
    def __init__(self, row_id: str = "source-1") -> None:
        self.row_id = row_id
        self.calls = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query: str, params=()):
        self.calls.append((query, params))
        return self

    def fetchone(self):
        return {"id": self.row_id}

    def commit(self):
        self.committed = True


def test_quake_severity_thresholds() -> None:
    assert quakes._severity(6.0) == "Extreme"
    assert quakes._severity(4.5) == "Severe"
    assert quakes._severity(3.0) == "Moderate"
    assert quakes._severity(1.0) == "Minor"


def test_fetch_earthquakes_uses_usgs_params(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": []}

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(quakes.requests, "get", fake_get)

    assert quakes.fetch_earthquakes(days=7, min_magnitude=2.5) == {"features": []}
    assert calls[0][0] == quakes.USGS_BASE
    assert calls[0][1]["params"]["minmagnitude"] == 2.5
    assert calls[0][1]["params"]["minlatitude"] == quakes.EXTENT["minlatitude"]


def test_normalize_earthquakes_filters_and_maps_records() -> None:
    payload = {
        "features": [
            {
                "id": "quake-1",
                "properties": {
                    "mag": 3.2,
                    "magType": "ml",
                    "place": "10 km S of Testville",
                    "time": 1_700_000_000_000,
                },
                "geometry": {"type": "Point", "coordinates": [-73.5, 41.0, 8.2]},
            },
            {"id": "missing-mag", "properties": {}, "geometry": {"coordinates": [-73, 41]}},
            {"id": "missing-coords", "properties": {"mag": 1.1}, "geometry": {"coordinates": []}},
        ]
    }

    records = quakes.normalize_earthquakes(payload)

    assert len(records) == 1
    record = records[0]
    assert record["event_type"] == "earthquake"
    assert record["severity"] == "Moderate"
    assert record["geometry"] == {"type": "Point", "coordinates": [-73.5, 41.0]}
    assert record["source_name"] == "usgs_earthquakes"
    assert record["source_tags"]["depth_km"] == 8.2
    assert record["headline"].startswith("M3.2 - 10 km S")


def test_quake_db_helpers() -> None:
    conn = FakeConnection()
    payload = {"features": [{"id": "quake-1"}]}
    record = quakes.normalize_earthquakes(
        {
            "features": [
                {
                    "id": "quake-1",
                    "properties": {"mag": 1.1, "place": "A place"},
                    "geometry": {"coordinates": [-74.0, 40.7]},
                }
            ]
        }
    )[0]

    source_id = quakes.upsert_source(
        conn,
        {
            "source_name": "usgs_earthquakes",
            "api_url": "https://example.test",
            "auth_required": False,
            "refresh_rate": "hourly",
        },
    )
    quakes.insert_raw_ingestion(conn, source_id, payload, days=30, min_mag=1.0)
    quakes.upsert_risk_events(conn, source_id, [record])

    assert source_id == "source-1"
    assert len(conn.calls) == 3
    assert json.loads(conn.calls[1][1][3])["days"] == 30
    assert conn.calls[2][1][0] == "earthquake"


def test_quake_run_dry_and_db(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "features": [
            {
                "id": "quake-1",
                "properties": {"mag": 1.1, "place": "A place"},
                "geometry": {"coordinates": [-74.0, 40.7]},
            }
        ]
    }
    conn = FakeConnection()
    monkeypatch.setattr(quakes, "RAW_DIR", tmp_path)
    monkeypatch.setattr(quakes, "fetch_earthquakes", lambda **kwargs: payload)
    monkeypatch.setattr(
        quakes,
        "load_contract",
        lambda: {
            "source_name": "usgs_earthquakes",
            "api_url": "https://example.test",
            "auth_required": False,
            "refresh_rate": "hourly",
        },
    )
    monkeypatch.setattr(quakes, "db_connection", lambda: conn)

    quakes.run(dry_run=True, days=1, min_magnitude=2.0)
    assert (tmp_path / "tri_state_earthquakes.json").exists()
    assert not conn.committed

    quakes.run(dry_run=False, days=1, min_magnitude=2.0)
    assert conn.committed


def test_quake_main_dispatch(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["usgs_quakes", "--dry-run", "--days", "3", "--min-magnitude", "2.2"],
    )
    monkeypatch.setattr(quakes, "run", lambda **kwargs: calls.append(kwargs))

    quakes.main()

    assert calls == [{"dry_run": True, "days": 3, "min_magnitude": 2.2}]


def test_fetch_sites_combines_state_rdb(monkeypatch) -> None:
    class FakeResponse:
        text = "# comment\nagency_cd\tsite_no\tstation_nm\n5s\t15s\t50s\nUSGS\t1\tOne\n"

        def raise_for_status(self):
            return None

    calls = []

    def fake_get(url, **kwargs):
        calls.append(kwargs["params"]["stateCd"])
        return FakeResponse()

    monkeypatch.setattr(water.requests, "get", fake_get)

    text = water.fetch_sites(["NY", "NJ"])

    assert calls == ["NY", "NJ"]
    assert text.count("agency_cd") == 1
    assert "USGS\t1\tOne" in text


def test_parse_rdb_and_normalize_sites() -> None:
    text = "\n".join(
        [
            "# comment",
            "agency_cd\tsite_no\tstation_nm\tsite_tp_cd\tdec_lat_va\tdec_long_va\thuc_cd\tdrain_area_va",
            "5s\t15s\t50s\t2s\t16s\t16s\t8s\t8s",
            "USGS\t01300000\tTest Stream\tST\t40.7\t-74.0\t02030104\t12.5",
            "USGS\tbad\tBad Coords\tST\tnope\t-74.0\t\t",
            "USGS\t\tMissing Site\tST\t40.8\t-74.1\t\t",
        ]
    )

    raw_records = water.parse_rdb(text)
    records = water.normalize_sites(raw_records)

    assert len(raw_records) == 3
    assert len(records) == 1
    record = records[0]
    assert record["entity_type"] == "location"
    assert record["subtype"] == "stream_gauge"
    assert record["source_name"] == "usgs_water"
    assert record["source_entity_id"] == "01300000"
    assert record["source_tags"]["site_type_label"] == "stream"
    assert record["source_tags"]["drain_area_sq_mi"] == 12.5


def test_water_db_helpers() -> None:
    conn = FakeConnection()
    records = water.normalize_sites(
        [
            {
                "agency_cd": "USGS",
                "site_no": "01300000",
                "station_nm": "Test Stream",
                "site_tp_cd": "ES",
                "dec_lat_va": "40.7",
                "dec_long_va": "-74.0",
                "huc_cd": "",
                "drain_area_va": "",
            }
        ]
    )

    source_id = water.upsert_source(
        conn,
        {
            "source_name": "usgs_water",
            "api_url": "https://example.test",
            "auth_required": False,
            "refresh_rate": "daily",
        },
    )
    water.upsert_geo_entities(conn, source_id, records)

    assert source_id == "source-1"
    assert len(conn.calls) == 2
    assert conn.calls[1][1][0] == "location"
    assert conn.calls[1][1][1] == "stream_gauge"


def test_water_run_dry_and_db(monkeypatch, tmp_path: Path) -> None:
    raw_text = "\n".join(
        [
            "agency_cd\tsite_no\tstation_nm\tsite_tp_cd\tdec_lat_va\tdec_long_va\thuc_cd\tdrain_area_va",
            "5s\t15s\t50s\t2s\t16s\t16s\t8s\t8s",
            "USGS\t01300000\tTest Stream\tLK\t40.7\t-74.0\t\t",
        ]
    )
    conn = FakeConnection()
    monkeypatch.setattr(water, "RAW_DIR", tmp_path)
    monkeypatch.setattr(water, "fetch_sites", lambda: raw_text)
    monkeypatch.setattr(
        water,
        "load_contract",
        lambda: {
            "source_name": "usgs_water",
            "api_url": "https://example.test",
            "auth_required": False,
            "refresh_rate": "daily",
        },
    )
    monkeypatch.setattr(water, "db_connection", lambda: conn)

    water.run(dry_run=True)
    assert (tmp_path / "tri_state_water_sites.rdb").exists()
    assert not conn.committed

    water.run(dry_run=False)
    assert conn.committed


def test_water_main_dispatch(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sys, "argv", ["usgs_water", "--dry-run"])
    monkeypatch.setattr(water, "run", lambda **kwargs: calls.append(kwargs))

    water.main()

    assert calls == [{"dry_run": True}]


@pytest.mark.parametrize("text", ["", "# only comments\nagency_cd\tsite_no"])
def test_parse_rdb_returns_empty_for_short_payload(text: str) -> None:
    assert water.parse_rdb(text) == []
