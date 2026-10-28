"""Integration tests for the public /state/nyc page."""

from __future__ import annotations

from datetime import datetime, timezone

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
async def test_nyc_state_page_renders_location_state(client, db_session):
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

    resp = await client.get("/state/nyc")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "New York, NY" in resp.text
    assert "WATCH" in resp.text
    assert "Risk score" in resp.text
    assert "API example" in resp.text
    assert "Watch button placeholder" in resp.text
    assert "weather_alert Extreme" in resp.text


@pytest.mark.asyncio
async def test_nyc_state_page_uses_normal_empty_state(client, db_session):
    await _seed_source(db_session, "noaa")

    resp = await client.get("/state/nyc")

    assert resp.status_code == 200
    assert "NORMAL" in resp.text
    assert "No active disruption signals" in resp.text
    assert "No active provenance records" in resp.text
