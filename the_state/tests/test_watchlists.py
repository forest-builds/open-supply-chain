"""Watchlist routes. Requires Postgres (see conftest.py)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from models.signal import Signal
from models.source import Source


async def _seed_source(db, name: str) -> Source:
    source = Source(name=name, source_type=name)
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def _seed_signal(
    db,
    *,
    source: Source,
    signal_type: str,
    severity: str,
    state_code: str = "NY",
) -> Signal:
    now = datetime.now(timezone.utc)
    signal = Signal(
        source_id=source.id,
        signal_type=signal_type,
        title=f"{signal_type} {severity}",
        severity=severity,
        observed_at=now,
        occurred_at=now,
        location={"state": state_code},
        attributes={},
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return signal


@pytest.mark.asyncio
async def test_create_and_get_watchlist(client):
    payload = {
        "name": "NYC Morning Ops",
        "place": "New York, NY",
        "time_window": "24h",
        "thresholds": {
            "notify_on_state": ["watch", "disrupted", "critical"],
            "min_score_delta": 0.1,
        },
        "delivery": {"channels": ["webhook"]},
    }

    create_resp = await client.post("/watchlists/", json=payload)
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["name"] == "NYC Morning Ops"
    assert body["place"] == "New York, NY"
    assert body["time_window"] == "24h"
    assert body["thresholds"]["min_score_delta"] == 0.1
    assert body["delivery"]["channels"] == ["webhook"]

    get_resp = await client.get(f"/watchlists/{body['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == body


@pytest.mark.asyncio
async def test_evaluate_watchlist_returns_location_state(client, db_session):
    noaa = await _seed_source(db_session, "noaa")
    fema = await _seed_source(db_session, "openfema")
    await _seed_signal(
        db_session,
        source=noaa,
        signal_type="weather_alert",
        severity="Extreme",
    )
    await _seed_signal(
        db_session,
        source=fema,
        signal_type="declaration",
        severity="Major Disaster",
    )
    create_resp = await client.post(
        "/watchlists/",
        json={"name": "NYC Morning Ops", "place": "New York, NY"},
    )
    watchlist_id = create_resp.json()["id"]

    eval_resp = await client.post(f"/watchlists/{watchlist_id}/evaluate")

    assert eval_resp.status_code == 200
    body = eval_resp.json()
    assert body["watchlist_id"] == watchlist_id
    assert body["previous_state"] is None
    assert body["current_state"] == "watch"
    assert body["current_score"] == pytest.approx(0.7)
    assert body["material_change"] is True
    assert body["location_state"]["place"] == "New York, NY"
    assert body["location_state"]["operational_state"] == "watch"
    assert len(body["location_state"]["provenance"]) == 2


@pytest.mark.asyncio
async def test_evaluate_watchlist_tracks_previous_result(client, db_session):
    noaa = await _seed_source(db_session, "noaa")
    await _seed_signal(
        db_session,
        source=noaa,
        signal_type="weather_alert",
        severity="Severe",
    )
    create_resp = await client.post(
        "/watchlists/",
        json={"name": "NYC Morning Ops", "place": "New York, NY"},
    )
    watchlist_id = create_resp.json()["id"]

    first = await client.post(f"/watchlists/{watchlist_id}/evaluate")
    second = await client.post(f"/watchlists/{watchlist_id}/evaluate")

    assert first.status_code == 200
    assert second.status_code == 200
    body = second.json()
    assert body["previous_state"] == "normal"
    assert body["previous_score"] == pytest.approx(0.2)
    assert body["score_delta"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_watchlist_not_found(client):
    missing_id = uuid4()
    resp = await client.get(f"/watchlists/{missing_id}")
    assert resp.status_code == 404

    eval_resp = await client.post(f"/watchlists/{missing_id}/evaluate")
    assert eval_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_multi_place_watchlist(client):
    create_resp = await client.post(
        "/watchlists/",
        json={
            "name": "Ops",
            "places": ["Brooklyn, NYC", "Manhattan, NYC"],
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["places"] == ["Brooklyn, NYC", "Manhattan, NYC"]
    # `place` mirrors places[0] for backward compatibility.
    assert body["place"] == "Brooklyn, NYC"

    get_resp = await client.get(f"/watchlists/{body['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == body


@pytest.mark.asyncio
async def test_evaluate_multi_place_rolls_up_highest_severity(client, db_session):
    fema = await _seed_source(db_session, "openfema")
    noaa = await _seed_source(db_session, "noaa")
    # Brooklyn: major disaster (0.40 -> elevated). Manhattan: severe (0.20 -> normal).
    bk = Signal(
        source_id=fema.id,
        signal_type="declaration",
        title="declaration Major Disaster",
        severity="Major Disaster",
        observed_at=datetime.now(timezone.utc),
        occurred_at=datetime.now(timezone.utc),
        location={"state": "NY", "borough": "BROOKLYN"},
        attributes={},
    )
    mn = Signal(
        source_id=noaa.id,
        signal_type="weather_alert",
        title="weather_alert Severe",
        severity="Severe",
        observed_at=datetime.now(timezone.utc),
        occurred_at=datetime.now(timezone.utc),
        location={"state": "NY", "borough": "MANHATTAN"},
        attributes={},
    )
    db_session.add_all([bk, mn])
    await db_session.commit()

    create_resp = await client.post(
        "/watchlists/",
        json={"name": "Ops", "places": ["Brooklyn, NYC", "Manhattan, NYC"]},
    )
    watchlist_id = create_resp.json()["id"]

    eval_resp = await client.post(f"/watchlists/{watchlist_id}/evaluate")

    assert eval_resp.status_code == 200
    body = eval_resp.json()
    assert len(body["entities"]) == 2
    by_place = {e["place"]: e for e in body["entities"]}
    assert by_place["Brooklyn, NYC"]["current_state"] == "elevated"
    assert by_place["Manhattan, NYC"]["current_state"] == "normal"
    # Rollup is the highest severity across all places.
    assert body["operational_state"] == "elevated"
    assert body["current_state"] == "elevated"
