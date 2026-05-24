import json
import sys
from pathlib import Path

import pytest

import pipelines.noaa as noaa
from pipelines.noaa import (
    alert_zone_geometry,
    fetch_active_alerts,
    fetch_stations,
    fetch_zone_geometry,
    insert_alerts_raw_ingestion,
    insert_raw_ingestion,
    load_alerts_contract,
    load_contract,
    normalize_alerts,
    normalize_stations,
    payload_hash,
    run,
    run_alerts,
    upsert_geo_entities,
    upsert_risk_events,
    upsert_source,
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


def test_normalize_stations_creates_observation_source_locations() -> None:
    records = normalize_stations(
        [
            {
                "id": "GHCND:TEST",
                "name": "TEST STATION",
                "latitude": 40.7,
                "longitude": -74.0,
                "elevation": 3,
                "mindate": "2020-01-01",
                "maxdate": "2026-01-01",
                "datacoverage": 0.9,
            }
        ]
    )

    assert records[0]["entity_type"] == "location"
    assert records[0]["subtype"] == "weather_station"
    assert records[0]["source_name"] == "noaa_cdo"


def test_normalize_alerts_creates_risk_events() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "alert-1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-74.0, 40.0], [-73.9, 40.0], [-73.9, 40.1], [-74.0, 40.0]]],
                },
                "properties": {
                    "id": "alert-1",
                    "event": "Flood Watch",
                    "severity": "Moderate",
                    "certainty": "Possible",
                    "urgency": "Future",
                    "headline": "Flood Watch headline",
                    "areaDesc": "Test County",
                    "effective": "2026-05-24T12:00:00-04:00",
                    "expires": "2026-05-25T12:00:00-04:00",
                },
            }
        ],
    }

    records = normalize_alerts(payload)

    assert records[0]["event_type"] == "Flood Watch"
    assert records[0]["source_name"] == "noaa_nws_alerts"
    assert records[0]["source_event_id"] == "alert-1"
    assert records[0]["geometry"]["type"] == "Polygon"


def test_load_contracts_read_yaml(monkeypatch, tmp_path: Path) -> None:
    source_contract = tmp_path / "source.yml"
    alerts_contract = tmp_path / "alerts.yml"
    source_contract.write_text("source_name: noaa_cdo\n")
    alerts_contract.write_text("source_name: noaa_nws_alerts\n")
    monkeypatch.setattr(noaa, "CONTRACT_PATH", source_contract)
    monkeypatch.setattr(noaa, "ALERTS_CONTRACT_PATH", alerts_contract)

    assert load_contract()["source_name"] == "noaa_cdo"
    assert load_alerts_contract()["source_name"] == "noaa_nws_alerts"


def test_fetch_stations_pages_until_total(monkeypatch) -> None:
    responses = [
        {
            "results": [{"id": "A"}],
            "metadata": {"resultset": {"count": 2}},
        },
        {
            "results": [{"id": "B"}],
            "metadata": {"resultset": {"count": 2}},
        },
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(*args, **kwargs):
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr(noaa.requests, "get", fake_get)

    assert fetch_stations("token") == [{"id": "A"}, {"id": "B"}]


def test_fetch_active_alerts_deduplicates_and_resolves_zones(monkeypatch) -> None:
    payloads = [
        {
            "features": [
                {
                    "id": "alert-1",
                    "geometry": None,
                    "properties": {"id": "alert-1", "affectedZones": ["zone-url"]},
                }
            ]
        },
        {
            "features": [
                {
                    "id": "alert-1",
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                    "properties": {"id": "alert-1"},
                }
            ]
        },
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    monkeypatch.setattr(noaa.requests, "get", lambda *args, **kwargs: FakeResponse(payloads.pop(0)))
    monkeypatch.setattr(
        noaa,
        "alert_zone_geometry",
        lambda feature, cache: {"type": "Point", "coordinates": [1, 1]},
    )

    result = fetch_active_alerts(["NY", "NJ"])

    assert len(result["features"]) == 1
    assert result["features"][0]["id"] == "alert-1"


def test_fetch_zone_geometry_returns_geometry(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"geometry": {"type": "Point", "coordinates": [0, 0]}}

    monkeypatch.setattr(noaa.requests, "get", lambda *args, **kwargs: FakeResponse())

    assert fetch_zone_geometry("zone-url")["type"] == "Point"


def test_alert_zone_geometry_uses_cache(monkeypatch) -> None:
    monkeypatch.setattr(
        noaa,
        "fetch_zone_geometry",
        lambda url: {
            "type": "Polygon",
            "coordinates": [[(0, 0), (1, 0), (1, 1), (0, 0)]],
        },
    )
    cache = {}
    feature = {"properties": {"affectedZones": ["zone-url", "zone-url"]}}

    geometry = alert_zone_geometry(feature, cache)

    assert geometry["type"] == "Polygon"
    assert "zone-url" in cache
    assert alert_zone_geometry({"properties": {"affectedZones": []}}, {}) is None


def test_payload_hash_is_stable() -> None:
    assert payload_hash({"b": 2, "a": 1}) == payload_hash({"a": 1, "b": 2})


def test_upsert_source_and_insert_helpers_execute_sql() -> None:
    conn = FakeConnection()
    contract = {
        "source_name": "noaa_cdo",
        "api_url": "https://example.test",
        "auth_required": True,
        "refresh_rate": "monthly",
        "license": "public",
        "attribution": "NOAA",
    }

    source_id = upsert_source(conn, contract)
    insert_raw_ingestion(conn, source_id, {"stations": []})
    insert_alerts_raw_ingestion(conn, source_id, {"features": []})

    assert source_id == "source-1"
    assert len(conn.calls) == 3


def test_upsert_geo_entities_and_risk_events_execute_per_record() -> None:
    conn = FakeConnection()
    station = normalize_stations(
        [{"id": "S", "name": "Station", "latitude": 40.0, "longitude": -74.0}]
    )[0]
    alert = normalize_alerts(
        {
            "features": [
                {
                    "id": "A",
                    "geometry": None,
                    "properties": {"event": "Alert", "id": "A"},
                }
            ]
        }
    )[0]

    upsert_geo_entities(conn, "source-1", [station])
    upsert_risk_events(conn, "source-1", [alert])

    assert len(conn.calls) == 2
    assert conn.calls[0][1][0] == "location"
    assert conn.calls[1][1][0] == "Alert"


def test_run_requires_noaa_token(monkeypatch) -> None:
    monkeypatch.delenv("NOAA_CDO_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="NOAA_CDO_TOKEN"):
        run(dry_run=True)


def test_run_dry_run_writes_raw(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NOAA_CDO_TOKEN", "token")
    monkeypatch.setattr(noaa, "RAW_DIR", tmp_path)
    monkeypatch.setattr(
        noaa,
        "fetch_stations",
        lambda token: [{"id": "S", "name": "Station", "latitude": 40.0, "longitude": -74.0}],
    )

    run(dry_run=True)

    payload = json.loads((tmp_path / "tri_state_stations.json").read_text())
    assert payload["stations"][0]["id"] == "S"


def test_run_alerts_loads_db_when_not_dry(monkeypatch, tmp_path: Path) -> None:
    conn = FakeConnection()
    monkeypatch.setattr(noaa, "RAW_DIR", tmp_path)
    monkeypatch.setattr(
        noaa,
        "fetch_active_alerts",
        lambda: {"features": [{"id": "A", "geometry": None, "properties": {"event": "Alert"}}]},
    )
    monkeypatch.setattr(noaa, "load_alerts_contract", lambda: {"source_name": "noaa_nws_alerts"})
    monkeypatch.setattr(noaa, "upsert_source", lambda conn, contract: "source-1")
    monkeypatch.setattr(noaa, "insert_alerts_raw_ingestion", lambda *args: conn.calls.append(args))
    monkeypatch.setattr(noaa, "upsert_risk_events", lambda *args: conn.calls.append(args))
    monkeypatch.setattr(noaa, "db_connection", lambda: conn)

    run_alerts(dry_run=False)

    assert conn.committed
    assert (tmp_path / "tri_state_active_alerts.json").exists()


def test_run_loads_stations_when_not_dry(monkeypatch, tmp_path: Path) -> None:
    conn = FakeConnection()
    monkeypatch.setenv("NOAA_CDO_TOKEN", "token")
    monkeypatch.setattr(noaa, "RAW_DIR", tmp_path)
    monkeypatch.setattr(
        noaa,
        "fetch_stations",
        lambda token: [{"id": "S", "name": "Station", "latitude": 40.0, "longitude": -74.0}],
    )
    monkeypatch.setattr(noaa, "load_contract", lambda: {"source_name": "noaa_cdo"})
    monkeypatch.setattr(noaa, "upsert_source", lambda conn, contract: "source-1")
    monkeypatch.setattr(noaa, "insert_raw_ingestion", lambda *args: conn.calls.append(args))
    monkeypatch.setattr(noaa, "upsert_geo_entities", lambda *args: conn.calls.append(args))
    monkeypatch.setattr(noaa, "db_connection", lambda: conn)

    run(dry_run=False)

    assert conn.committed


def test_noaa_main_dispatches_dataset(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(sys, "argv", ["noaa", "--dataset", "alerts", "--dry-run"])
    monkeypatch.setattr(noaa, "run_alerts", lambda dry_run: calls.append(("alerts", dry_run)))

    noaa.main()

    assert calls == [("alerts", True)]
