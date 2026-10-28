"""Integration tests for GET /state/location. Requires Postgres (see conftest)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from models.signal import Signal
from models.source import Source


async def _seed_source(db, name: str = "noaa") -> Source:
    src = Source(name=name, source_type=name)
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return src


async def _seed_signal(
    db,
    *,
    source: Source,
    signal_type: str,
    severity: str,
    state_code: str,
    borough: str | None = None,
    occurred_at: datetime | None = None,
    location_key: str = "location",
) -> Signal:
    occurred_at = occurred_at or datetime.now(timezone.utc)
    location = {"state": state_code} if location_key == "location" else None
    if location is not None and borough is not None:
        location["borough"] = borough
    attributes = {"state": state_code} if location_key == "attributes" else {}
    if attributes and borough is not None:
        attributes["borough"] = borough
    sig = Signal(
        source_id=source.id,
        signal_type=signal_type,
        title=f"{signal_type} {severity} {state_code}",
        severity=severity,
        observed_at=occurred_at,
        occurred_at=occurred_at,
        location=location,
        attributes=attributes,
    )
    db.add(sig)
    await db.commit()
    await db.refresh(sig)
    return sig


@pytest.mark.asyncio
async def test_state_location_no_signals_returns_normal(client, db_session):
    await _seed_source(db_session, "noaa")
    resp = await client.get("/state/location", params={"place": "New York, NY"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state_code"] == "NY"
    assert body["operational_state"] == "normal"
    assert body["risk_score"] == 0.0
    assert body["confidence"] == 0.0
    assert body["active_signals"] == []
    assert body["provenance"] == []
    assert "No active disruption signals" in body["summary"]


@pytest.mark.asyncio
async def test_state_location_with_severe_weather_alert(client, db_session):
    src = await _seed_source(db_session, "noaa")
    await _seed_signal(
        db_session,
        source=src,
        signal_type="weather_alert",
        severity="Severe",
        state_code="NY",
    )
    resp = await client.get("/state/location", params={"place": "New York, NY"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_score"] == pytest.approx(0.20)
    assert body["operational_state"] == "normal"  # 0.20 < 0.25 band
    assert len(body["active_signals"]) == 1
    assert body["active_signals"][0]["signal_type"] == "weather_alert"
    assert body["active_signals"][0]["source"] == "noaa"
    assert len(body["provenance"]) == 1


@pytest.mark.asyncio
async def test_state_location_combines_weather_and_declaration(client, db_session):
    noaa = await _seed_source(db_session, "noaa")
    fema = await _seed_source(db_session, "openfema")
    await _seed_signal(
        db_session,
        source=noaa,
        signal_type="weather_alert",
        severity="Extreme",
        state_code="FL",
    )
    await _seed_signal(
        db_session,
        source=fema,
        signal_type="declaration",
        severity="Major Disaster",
        state_code="FL",
        location_key="attributes",
    )
    resp = await client.get("/state/location", params={"place": "Miami, FL"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_score"] == pytest.approx(0.70)
    assert body["operational_state"] == "watch"
    assert len(body["active_signals"]) == 2
    assert len(body["drivers"]) == 2
    assert len(body["recommended_actions"]) >= 1


@pytest.mark.asyncio
async def test_state_location_excludes_other_states(client, db_session):
    src = await _seed_source(db_session, "noaa")
    await _seed_signal(
        db_session,
        source=src,
        signal_type="weather_alert",
        severity="Severe",
        state_code="CA",
    )
    resp = await client.get("/state/location", params={"place": "New York, NY"})
    assert resp.status_code == 200
    assert resp.json()["active_signals"] == []


@pytest.mark.asyncio
async def test_state_location_can_filter_nyc_borough(client, db_session):
    src = await _seed_source(db_session, "nyc-311")
    await _seed_signal(
        db_session,
        source=src,
        signal_type="civic_complaint",
        severity="High",
        state_code="NY",
        borough="BROOKLYN",
    )
    await _seed_signal(
        db_session,
        source=src,
        signal_type="civic_complaint",
        severity="High",
        state_code="NY",
        borough="QUEENS",
    )

    resp = await client.get("/state/location", params={"place": "Brooklyn, NYC"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_score"] == pytest.approx(0.10)
    assert len(body["active_signals"]) == 1
    assert body["active_signals"][0]["title"] == "civic_complaint High NY"


@pytest.mark.asyncio
async def test_state_location_excludes_signals_outside_window(client, db_session):
    src = await _seed_source(db_session, "noaa")
    old = datetime.now(timezone.utc) - timedelta(days=10)
    await _seed_signal(
        db_session,
        source=src,
        signal_type="weather_alert",
        severity="Severe",
        state_code="NY",
        occurred_at=old,
    )
    resp = await client.get(
        "/state/location",
        params={"place": "New York, NY", "time_window": "24h"},
    )
    assert resp.status_code == 200
    assert resp.json()["active_signals"] == []


@pytest.mark.asyncio
async def test_state_location_includes_signals_inside_longer_window(client, db_session):
    src = await _seed_source(db_session, "noaa")
    old = datetime.now(timezone.utc) - timedelta(days=10)
    await _seed_signal(
        db_session,
        source=src,
        signal_type="weather_alert",
        severity="Severe",
        state_code="NY",
        occurred_at=old,
    )
    resp = await client.get(
        "/state/location",
        params={"place": "New York, NY", "time_window": "30d"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["active_signals"]) == 1


async def _seed_raw_signal(db, *, source: Source, location: dict) -> Signal:
    now = datetime.now(timezone.utc)
    sig = Signal(
        source_id=source.id,
        signal_type="civic_complaint",
        title="civic_complaint High",
        severity="High",
        observed_at=now,
        occurred_at=now,
        location=location,
        attributes={},
    )
    db.add(sig)
    await db.commit()
    await db.refresh(sig)
    return sig


@pytest.mark.asyncio
async def test_state_location_includes_borough_sub_locations(client, db_session):
    src = await _seed_source(db_session, "nyc-311")
    await _seed_raw_signal(db_session, source=src, location={"state": "NY", "borough": "BROOKLYN"})
    await _seed_raw_signal(db_session, source=src, location={"state": "NY", "borough": "QUEENS"})

    resp = await client.get("/state/location", params={"place": "New York, NY"})

    assert resp.status_code == 200
    subs = resp.json()["sub_locations"]
    assert {s["name"] for s in subs} == {"BROOKLYN", "QUEENS"}
    assert all(s["granularity"] == "borough" for s in subs)
    assert all(s["signal_count"] == 1 for s in subs)


@pytest.mark.asyncio
async def test_state_location_includes_zip_sub_locations_for_borough(client, db_session):
    src = await _seed_source(db_session, "nyc-311")
    await _seed_raw_signal(
        db_session,
        source=src,
        location={"state": "NY", "borough": "BROOKLYN", "zip": "11201"},
    )
    await _seed_raw_signal(
        db_session,
        source=src,
        location={"state": "NY", "borough": "BROOKLYN", "zip": "11215"},
    )

    resp = await client.get("/state/location", params={"place": "Brooklyn, NYC"})

    assert resp.status_code == 200
    subs = resp.json()["sub_locations"]
    assert {s["name"] for s in subs} == {"11201", "11215"}
    assert all(s["granularity"] == "zip" for s in subs)


@pytest.mark.asyncio
async def test_state_location_rejects_unknown_place(client):
    resp = await client.get("/state/location", params={"place": "Atlantis"})
    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_state_location_rejects_invalid_time_window(client):
    resp = await client.get(
        "/state/location",
        params={"place": "New York, NY", "time_window": "bogus"},
    )
    assert resp.status_code == 400
