"""Append-only state history (BUILD Task 2.3). Requires Postgres."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_every_call_appends_an_immutable_snapshot(client):
    for _ in range(3):
        r = await client.get("/state/location", params={"place": "New York, NY"})
        assert r.status_code == 200

    hist = await client.get("/state/location/history", params={"place": "New York, NY"})
    assert hist.status_code == 200
    rows = hist.json()
    assert len(rows) == 3
    # Newest first, and each entry carries the decision-relevant fields.
    times = [r["computed_at"] for r in rows]
    assert times == sorted(times, reverse=True)
    assert {"operational_state", "risk_score", "confidence", "signal_count"} <= set(rows[0])


@pytest.mark.asyncio
async def test_history_is_isolated_per_place(client):
    await client.get("/state/location", params={"place": "New York, NY"})
    await client.get("/state/location", params={"place": "Brooklyn, NYC"})

    bk = await client.get("/state/location/history", params={"place": "Brooklyn, NYC"})
    assert bk.status_code == 200
    assert len(bk.json()) == 1


@pytest.mark.asyncio
async def test_history_respects_the_time_window(client):
    await client.get("/state/location", params={"place": "New York, NY"})
    empty = await client.get(
        "/state/location/history",
        params={
            "place": "New York, NY",
            "from_dt": "2000-01-01T00:00:00Z",
            "to_dt": "2000-01-02T00:00:00Z",
        },
    )
    assert empty.status_code == 200
    assert empty.json() == []


@pytest.mark.asyncio
async def test_history_rejects_unresolvable_place(client):
    resp = await client.get("/state/location/history", params={"place": "Atlantis"})
    assert resp.status_code == 400
