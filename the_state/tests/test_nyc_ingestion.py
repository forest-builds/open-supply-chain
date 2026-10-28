from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from ingestion.nyc import (
    NycOpenDataCollector,
    SocrataClient,
    normalize_311_complaint,
    normalize_dot_street_closure,
    normalize_hpd_violation,
    normalize_nyc_event,
)
from ingestion.nyc.socrata import _format_soql_datetime


@pytest.mark.asyncio
async def test_socrata_client_queries_dataset_with_soql_params():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["limit"] = request.url.params["$limit"]
        captured["where"] = request.url.params["$where"]
        captured["order"] = request.url.params["$order"]
        return httpx.Response(200, json=[{"unique_key": "1"}])

    http_client = httpx.AsyncClient(
        base_url="https://data.cityofnewyork.us/resource",
        transport=httpx.MockTransport(handler),
    )
    client = SocrataClient(http_client=http_client)

    rows = await client.query(
        "erm2-nwe9",
        where="borough='BROOKLYN'",
        limit=25,
        order="created_date DESC",
    )

    assert rows == [{"unique_key": "1"}]
    assert captured == {
        "path": "/resource/erm2-nwe9.json",
        "limit": "25",
        "where": "borough='BROOKLYN'",
        "order": "created_date DESC",
    }
    await http_client.aclose()


@pytest.mark.asyncio
async def test_nyc_collector_fetches_and_normalizes_311():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "unique_key": "311-1",
                    "created_date": "2026-05-11T12:00:00",
                    "complaint_type": "HEAT/HOT WATER",
                    "descriptor": "No Heat",
                    "borough": "BROOKLYN",
                    "incident_zip": "11201",
                }
            ],
        )

    http_client = httpx.AsyncClient(
        base_url="https://data.cityofnewyork.us/resource",
        transport=httpx.MockTransport(handler),
    )
    collector = NycOpenDataCollector(SocrataClient(http_client=http_client))

    signals = await collector.collect("311", limit=1)

    assert len(signals) == 1
    assert signals[0].source_name == "nyc-311"
    assert signals[0].signal_type == "civic_complaint"
    assert signals[0].severity == "High"
    assert signals[0].location["borough"] == "BROOKLYN"
    await http_client.aclose()


def test_normalize_311_complaint():
    signal = normalize_311_complaint(
        {
            "unique_key": "311-1",
            "created_date": "2026-05-11T12:00:00",
            "complaint_type": "Noise - Residential",
            "descriptor": "Loud Music/Party",
            "borough": "QUEENS",
            "incident_zip": "11375",
            "latitude": "40.72",
            "longitude": "-73.84",
            "status": "Open",
        }
    )

    assert signal.external_id == "311-1"
    assert signal.signal_type == "civic_complaint"
    assert signal.severity == "Medium"
    assert signal.title == "Noise - Residential: Loud Music/Party"
    assert signal.location == {
        "state": "NY",
        "city": "New York",
        "borough": "QUEENS",
        "zip": "11375",
        "latitude": 40.72,
        "longitude": -73.84,
    }


def test_normalize_dot_street_closure():
    signal = normalize_dot_street_closure(
        {
            "segmentid": "seg-1",
            "purpose": "Emergency street work",
            "boro": "M",
            "onstreetname": "BROADWAY",
            "fromstreetname": "W 14 ST",
            "tostreetname": "W 23 ST",
            "work_start_date": "2026-05-11T08:00:00",
            "work_end_date": "2026-05-11T18:00:00",
        }
    )

    assert signal.source_name == "nyc-dot-street-closures"
    assert signal.signal_type == "street_closure"
    assert signal.severity == "High"
    assert signal.location["borough"] == "MANHATTAN"
    assert "BROADWAY" in signal.title


def test_normalize_nyc_event():
    signal = normalize_nyc_event(
        {
            "event_id": "event-1",
            "event_name": "Neighborhood Parade",
            "event_type": "Parade",
            "event_borough": "Bronx",
            "event_location": "Grand Concourse",
            "start_date_time": "2026-05-12T09:00:00",
            "end_date_time": "2026-05-12T11:00:00",
        }
    )

    assert signal.source_name == "nyc-events"
    assert signal.signal_type == "public_event"
    assert signal.severity == "Medium"
    assert signal.location["borough"] == "BRONX"


def test_normalize_hpd_violation():
    signal = normalize_hpd_violation(
        {
            "violationid": "hpd-1",
            "inspectiondate": "2026-05-10T15:30:00",
            "class": "C",
            "novdescription": "Immediately hazardous violation",
            "boroid": "3",
            "zip": "11216",
            "nta": "BK61",
            "buildingid": "building-1",
            "bbl": "3012340056",
        }
    )

    assert signal.source_name == "nyc-hpd-violations"
    assert signal.signal_type == "housing_violation"
    assert signal.severity == "High"
    assert signal.location["borough"] == "BROOKLYN"
    assert signal.location["nta"] == "BK61"
    assert signal.observed_at == datetime(2026, 5, 10, 15, 30, tzinfo=timezone.utc)


def test_format_soql_datetime_uses_plain_utc():
    value = datetime(2026, 5, 11, 2, 38, 18, tzinfo=timezone.utc)

    assert _format_soql_datetime(value) == "2026-05-11T02:38:18"
