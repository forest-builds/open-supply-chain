from __future__ import annotations

from pathlib import Path

import pytest

from pipelines import ais, eia, epa, gdacs, usaspending


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeConn:
    def __init__(self, source_id: str = "source-1"):
        self.source_id = source_id
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None):
        self.calls.append((sql, params))
        return self

    def fetchone(self) -> dict[str, str]:
        return {"id": self.source_id}

    def commit(self) -> None:
        self.calls.append(("COMMIT", None))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_ais_fetch_accepts_alternate_shapes_and_normalize_fallbacks():
    raw = [
        {
            "MMSI": "987654321",
            "LON": "-73.9",
            "LAT": "40.8",
            "SHIPNAME": "",
            "SHIPTYPE": "999",
            "SPEED": "fast",
            "COURSE": "north",
        },
        {"MMSI": "bad-coords", "LON": "x", "LAT": "40.8"},
    ]

    records = ais.normalize_vessels(raw)

    assert len(records) == 1
    assert records[0]["name"] == "MMSI 987654321"
    assert records[0]["source_tags"]["ship_type"] == "type_999"
    assert records[0]["source_tags"]["speed_knots"] is None
    assert records[0]["source_tags"]["heading_deg"] is None


def test_ais_fetch_normalize_hash_and_db_paths(monkeypatch):
    raw = [
        {
            "MMSI": "123456789",
            "LONGITUDE": "-74.0",
            "LATITUDE": "40.7",
            "NAME": "Cargo One",
            "TYPE": "70",
            "SPEED": "12.5",
            "HEADING": "91",
            "DESTINATION": "NEWARK",
        },
        {"MMSI": "bad", "LONGITUDE": "999", "LATITUDE": "40.7"},
        {"LONGITUDE": "-74.0", "LATITUDE": "40.7"},
    ]
    monkeypatch.setattr(ais.requests, "get", lambda *_, **__: FakeResponse([{"meta": 1}, raw]))

    fetched = ais.fetch_vessels("key")
    records = ais.normalize_vessels(fetched)
    conn = FakeConn()
    source_id = ais.upsert_source(
        conn,
        {
            "source_name": "ais_vessels",
            "api_url": "http://example.test",
            "auth_required": True,
            "refresh_rate": "hourly",
        },
    )
    ais.insert_raw_ingestion(conn, source_id, fetched)
    ais.upsert_geo_entities(conn, source_id, records)

    assert fetched == raw
    assert ais.payload_hash(raw) == ais.payload_hash(list(raw))
    assert len(records) == 1
    assert records[0]["source_tags"]["ship_type"] == "cargo"
    assert records[0]["source_tags"]["speed_knots"] == 12.5
    assert any("raw_ingestions" in sql for sql, _ in conn.calls)
    assert any("geo_entities" in sql for sql, _ in conn.calls)


def test_ais_run_skips_without_api_key(monkeypatch, capsys):
    monkeypatch.delenv("AIS_API_KEY", raising=False)

    ais.run()

    assert "AIS_API_KEY" in capsys.readouterr().out


def test_ais_run_loads_when_not_dry(monkeypatch, tmp_path):
    conn = FakeConn()
    monkeypatch.setenv("AIS_API_KEY", "key")
    monkeypatch.setattr(ais, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ais, "fetch_vessels", lambda api_key: [{"MMSI": "1", "LON": "-74", "LAT": "40"}])
    monkeypatch.setattr(
        ais,
        "load_contract",
        lambda: {
            "source_name": "ais_vessels",
            "api_url": "http://example.test",
            "auth_required": True,
            "refresh_rate": "hourly",
        },
    )
    monkeypatch.setattr(ais, "db_connection", lambda: conn)

    ais.run(dry_run=False)

    assert ("COMMIT", None) in conn.calls
    assert (tmp_path / "tri_state_vessels.json").exists()


def test_eia_fetch_normalize_hash_and_run_dry(monkeypatch, tmp_path):
    payload = {
        "response": {
            "data": [
                {
                    "plantCode": "100",
                    "latitude": "40.1",
                    "longitude": "-74.1",
                    "plantName": "Grid Plant",
                    "energy_source_code": "NG",
                    "nameplate-capacity-mw": "22.5",
                    "generatorId": "A",
                    "period": "2025",
                },
                {"plantCode": "100", "latitude": "40.2", "longitude": "-74.2"},
                {"plantCode": "bad", "latitude": "", "longitude": "-74.2"},
            ]
        }
    }
    monkeypatch.setattr(eia.requests, "get", lambda *_, **__: FakeResponse(payload))
    monkeypatch.setattr(eia, "RAW_DIR", tmp_path)
    monkeypatch.setenv("EIA_API_KEY", "key")

    fetched = eia.fetch_generators("key", "NJ")
    records = eia.normalize_generators(fetched, "NJ")
    eia.run(dry_run=True)
    conn = FakeConn()
    source_id = eia.upsert_source(
        conn,
        {
            "source_name": "eia",
            "api_url": "http://example.test",
            "auth_required": True,
            "refresh_rate": "monthly",
        },
    )
    eia.insert_raw_ingestion(conn, source_id, "NJ", fetched)
    eia.upsert_geo_entities(conn, source_id, records)

    assert eia.payload_hash(payload) == eia.payload_hash(dict(payload))
    assert len(records) == 1
    assert records[0]["source_tags"]["nameplate_capacity_mw"] == 22.5
    assert (tmp_path / "generators_nj.json").exists()
    assert any("raw_ingestions" in sql for sql, _ in conn.calls)


def test_eia_run_loads_and_handles_http_error(monkeypatch, tmp_path):
    class BrokenResponse(FakeResponse):
        def raise_for_status(self) -> None:
            raise eia.requests.HTTPError("bad state")

    payload = {
        "response": {
            "data": [
                {
                    "plant-id": "200",
                    "latitude": "40.1",
                    "longitude": "-74.1",
                    "plant-name": "Fallback Plant",
                    "nameplate-capacity-mw": "bad",
                }
            ]
        }
    }
    calls = []

    def fake_fetch(api_key: str, state: str):
        calls.append(state)
        if state == "NY":
            raise eia.requests.HTTPError("bad state")
        return payload

    conn = FakeConn()
    monkeypatch.setenv("EIA_API_KEY", "key")
    monkeypatch.setattr(eia, "RAW_DIR", tmp_path)
    monkeypatch.setattr(eia, "fetch_generators", fake_fetch)
    monkeypatch.setattr(
        eia,
        "load_contract",
        lambda: {
            "source_name": "eia",
            "api_url": "http://example.test",
            "auth_required": True,
            "refresh_rate": "monthly",
        },
    )
    monkeypatch.setattr(eia, "db_connection", lambda: conn)

    assert isinstance(BrokenResponse({}), FakeResponse)
    eia.run(dry_run=False)
    records = eia.normalize_generators(payload, "NJ")

    assert calls == ["NY", "NJ", "CT"]
    assert records[0]["source_tags"]["nameplate_capacity_mw"] is None
    assert ("COMMIT", None) in conn.calls


def test_eia_run_skips_without_api_key(monkeypatch, capsys):
    monkeypatch.delenv("EIA_API_KEY", raising=False)

    eia.run()

    assert "EIA_API_KEY" in capsys.readouterr().out


def test_epa_fetch_normalize_and_run_dry(monkeypatch, tmp_path):
    payload = {
        "Results": {
            "Facilities": [
                {
                    "RegistryID": "1101",
                    "FacilityLatitude": "40.3",
                    "FacilityLongitude": "-74.3",
                    "FacilityName": "Hazmat Place",
                    "FacilityCity": "Newark",
                },
                {"RegistryID": "bad", "FacilityLatitude": "", "FacilityLongitude": "-74.3"},
            ]
        }
    }
    monkeypatch.setattr(epa.requests, "get", lambda *_, **__: FakeResponse(payload))
    monkeypatch.setattr(epa, "RAW_DIR", tmp_path)

    fetched = epa.fetch_facilities("NJ", "RCRA")
    records = epa.normalize_facilities(fetched, "hazmat_site", "RCRA")
    epa.run(dry_run=True)
    conn = FakeConn()
    source_id = epa.upsert_source(
        conn,
        {
            "source_name": "epa_echo",
            "api_url": "http://example.test",
            "auth_required": False,
            "refresh_rate": "weekly",
        },
    )
    epa.upsert_geo_entities(conn, source_id, records)

    assert epa.payload_hash(payload) == epa.payload_hash(dict(payload))
    assert len(records) == 1
    assert records[0]["source_tags"]["program"] == "RCRA"
    assert (tmp_path / "nj_rcra.json").exists()
    assert any("geo_entities" in sql for sql, _ in conn.calls)


def test_epa_run_loads_and_handles_http_error(monkeypatch, tmp_path):
    payload = {
        "Results": {
            "FacilitiesExtract": [
                {
                    "FacilityID": "2202",
                    "Latitude83": "40.6",
                    "Longitude83": "-74.6",
                    "FacilityNm": "EPA Fallback",
                    "CityName": "Jersey City",
                }
            ]
        }
    }
    calls = []

    def fake_fetch(state: str, program_code: str):
        calls.append((state, program_code))
        if state == "NY" and program_code == "CERCLA":
            raise epa.requests.HTTPError("too broad")
        return payload

    conn = FakeConn()
    monkeypatch.setattr(epa, "RAW_DIR", tmp_path)
    monkeypatch.setattr(epa, "fetch_facilities", fake_fetch)
    monkeypatch.setattr(
        epa,
        "load_contract",
        lambda: {
            "source_name": "epa_echo",
            "api_url": "http://example.test",
            "auth_required": False,
            "refresh_rate": "weekly",
        },
    )
    monkeypatch.setattr(epa, "db_connection", lambda: conn)

    epa.run(dry_run=False)
    records = epa.normalize_facilities(payload, "superfund_site", "CERCLA")

    assert records[0]["name"] == "EPA Fallback"
    assert ("COMMIT", None) in conn.calls
    assert ("NY", "CERCLA") in calls


def test_gdacs_parse_normalize_hash_and_db_paths(monkeypatch, tmp_path):
    payload = {
        "features": [
            {
                "geometry": None,
                "properties": {
                    "eventid": 7,
                    "eventtype": "FL",
                    "eventname": "Flood",
                    "alertlevel": "Orange",
                    "country": "USA",
                    "fromdate": "2026-05-01T01:02:03",
                    "todate": "2026-05-02",
                    "lat": "40.4",
                    "lon": "-74.4",
                    "severitydata": {"severity": 3},
                },
            },
            {"properties": {"eventtype": "EQ"}},
        ]
    }
    monkeypatch.setattr(gdacs.requests, "get", lambda *_, **__: FakeResponse(payload))
    monkeypatch.setattr(gdacs, "RAW_DIR", tmp_path)

    fetched = gdacs.fetch_events()
    records = gdacs.normalize_events(fetched)
    gdacs.run(dry_run=True)
    conn = FakeConn()
    source_id = gdacs.upsert_source(
        conn,
        {
            "source_name": "gdacs",
            "api_url": "http://example.test",
            "auth_required": False,
            "refresh_rate": "hourly",
        },
    )
    gdacs.insert_raw_ingestion(conn, source_id, fetched)
    gdacs.upsert_risk_events(conn, source_id, records)

    assert gdacs._parse_dt("not a date") is None
    assert gdacs.payload_hash(payload) == gdacs.payload_hash(dict(payload))
    assert len(records) == 1
    assert records[0]["severity"] == "Severe"
    assert records[0]["geometry"]["type"] == "Point"
    assert (tmp_path / "global_disasters.json").exists()
    assert any("risk_events" in sql for sql, _ in conn.calls)


def test_gdacs_run_loads_with_existing_geometry(monkeypatch, tmp_path):
    payload = {
        "features": [
            {
                "geometry": {"type": "Point", "coordinates": [-74.0, 40.0]},
                "properties": {
                    "eventid": 8,
                    "eventtype": "XX",
                    "name": "Mystery Event",
                    "alertlevel": "Red",
                    "fromdate": "2026-05-01 01:02:03",
                    "todate": "not a date",
                    "severity": {"value": 5},
                },
            }
        ]
    }
    conn = FakeConn()
    monkeypatch.setattr(gdacs, "RAW_DIR", tmp_path)
    monkeypatch.setattr(gdacs, "fetch_events", lambda: payload)
    monkeypatch.setattr(
        gdacs,
        "load_contract",
        lambda: {
            "source_name": "gdacs",
            "api_url": "http://example.test",
            "auth_required": False,
            "refresh_rate": "hourly",
        },
    )
    monkeypatch.setattr(gdacs, "db_connection", lambda: conn)

    gdacs.run(dry_run=False)
    records = gdacs.normalize_events(payload)

    assert records[0]["event_type"] == "xx"
    assert records[0]["severity"] == "Extreme"
    assert records[0]["expires_at"] is None
    assert ("COMMIT", None) in conn.calls


def test_usaspending_fetch_normalize_hash_and_run_dry(monkeypatch, tmp_path):
    page_payload = {
        "results": [
            {
                "Award ID": "A1",
                "Recipient Name": "Logistics Co",
                "recipient_uei": "UEI1",
                "NAICS Code": "4841",
                "NAICS Description": "Trucking",
                "Award Amount": "1000",
                "Awarding Agency": "Agency",
                "Period of Performance Current End Date": "2026-01-01",
                "recipient_location": {
                    "latitude": "40.5",
                    "longitude": "-74.5",
                    "state_code": "NJ",
                    "city_name": "Newark",
                },
            },
            {
                "Award ID": "A2",
                "recipient_uei": "UEI2",
                "recipient_location": {"latitude": "", "longitude": "-74.5"},
            },
        ],
        "page_metadata": {"total": 2},
    }
    monkeypatch.setattr(usaspending.requests, "post", lambda *_, **__: FakeResponse(page_payload))
    monkeypatch.setattr(usaspending, "RAW_DIR", tmp_path)

    fetched = usaspending.fetch_awards_page(1)
    records = usaspending.normalize_awards(fetched["results"])
    usaspending.run(dry_run=True)
    conn = FakeConn()
    source_id = usaspending.upsert_source(
        conn,
        {
            "source_name": "usaspending",
            "api_url": "http://example.test",
            "auth_required": False,
            "refresh_rate": "monthly",
        },
    )
    usaspending.insert_raw_ingestion(conn, source_id, fetched["results"])
    usaspending.upsert_geo_entities(conn, source_id, records)

    assert usaspending.payload_hash(page_payload) == usaspending.payload_hash(dict(page_payload))
    assert len(records) == 1
    assert records[0]["source_entity_id"] == "UEI1"
    assert records[0]["source_tags"]["award_amount_usd"] == 1000.0
    assert (tmp_path / "logistics_contractors.json").exists()
    assert any("raw_ingestions" in sql for sql, _ in conn.calls)


def test_usaspending_run_loads_dedups_and_handles_errors(monkeypatch, tmp_path):
    pages = {
        1: {
            "results": [
                {
                    "Award ID": "A1",
                    "Recipient Name": "Logistics Co",
                    "recipient_uei": "UEI1",
                    "Award Amount": "100",
                    "recipient_location": {"latitude": "40.5", "longitude": "-74.5"},
                },
                {
                    "Award ID": "A2",
                    "Recipient Name": "Logistics Co Better",
                    "recipient_uei": "UEI1",
                    "Award Amount": "200",
                    "recipient_location": {"latitude": "40.5", "longitude": "-74.5"},
                },
                {
                    "Award ID": "A3",
                    "Award Amount": "bad",
                    "recipient_location": {"latitude": "40.6", "longitude": "-74.6"},
                },
            ],
            "page_metadata": {"total": usaspending.PAGE_SIZE + 1},
        }
    }

    def fake_fetch(page: int):
        if page == 2:
            raise usaspending.requests.HTTPError("stop")
        return pages[page]

    conn = FakeConn()
    monkeypatch.setattr(usaspending, "RAW_DIR", tmp_path)
    monkeypatch.setattr(usaspending, "fetch_awards_page", fake_fetch)
    monkeypatch.setattr(
        usaspending,
        "load_contract",
        lambda: {
            "source_name": "usaspending",
            "api_url": "http://example.test",
            "auth_required": False,
            "refresh_rate": "monthly",
        },
    )
    monkeypatch.setattr(usaspending, "db_connection", lambda: conn)

    usaspending.run(dry_run=False)
    records = usaspending.normalize_awards(pages[1]["results"])

    assert len(records) == 3
    assert records[-1]["source_tags"]["award_amount_usd"] is None
    assert ("COMMIT", None) in conn.calls


@pytest.mark.parametrize("module", [ais, eia, epa, gdacs, usaspending])
def test_pipeline_main_dispatches_dry_run(monkeypatch, module):
    called = []
    monkeypatch.setattr(module, "run", lambda dry_run=False: called.append(dry_run))
    monkeypatch.setattr("sys.argv", [module.__name__, "--dry-run"])

    module.main()

    assert called == [True]


@pytest.mark.parametrize(
    ("module", "contract_name"),
    [
        (ais, "ais_vessels"),
        (eia, "eia"),
        (epa, "epa_echo"),
        (gdacs, "gdacs"),
        (usaspending, "usaspending"),
    ],
)
def test_new_source_contracts_load(module, contract_name: str):
    path = Path(module.CONTRACT_PATH)

    contract = module.load_contract()

    assert path.exists()
    assert contract["source_name"] == contract_name
