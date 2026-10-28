"""Public brief verification endpoint. Requires Postgres."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from models.signal import Signal
from models.source import Source


async def _seed(db) -> None:
    noaa = Source(name="noaa", source_type="noaa")
    fema = Source(name="openfema", source_type="openfema")
    db.add_all([noaa, fema])
    await db.flush()
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            Signal(
                source_id=noaa.id,
                signal_type="weather_alert",
                title="weather_alert Extreme",
                severity="Extreme",
                observed_at=now,
                occurred_at=now,
                location={"state": "NY"},
                attributes={},
            ),
            Signal(
                source_id=fema.id,
                signal_type="declaration",
                title="declaration Major Disaster",
                severity="Major Disaster",
                observed_at=now,
                occurred_at=now,
                location={"state": "NY"},
                attributes={},
            ),
        ]
    )
    await db.commit()


async def _make_brief(client, db_session) -> dict:
    await _seed(db_session)
    wl = await client.post("/watchlists/", json={"name": "ops", "place": "New York, NY"})
    wid = wl.json()["id"]
    await client.post(f"/watchlists/{wid}/evaluate")
    gen = await client.post("/briefs/generate", json={"watchlist_id": wid})
    assert gen.status_code == 201
    return gen.json()


@pytest.mark.asyncio
async def test_verify_endpoint_attests_match(client, db_session):
    body = await _make_brief(client, db_session)

    resp = await client.get(f"/briefs/{body['id']}/verify")
    assert resp.status_code == 200
    v = resp.json()
    assert v["verified"] is True
    assert v["algorithm"] == "sha256"
    assert v["stored_hash"] == v["computed_hash"] == body["content_hash"]
    assert v["canonical_url"].endswith(f"/briefs/{body['id']}/view")


@pytest.mark.asyncio
async def test_verify_is_independently_reproducible(client, db_session):
    body = await _make_brief(client, db_session)
    v = (await client.get(f"/briefs/{body['id']}/verify")).json()
    # A third party recomputes from `content` alone and must match.
    independent = "sha256:" + hashlib.sha256(body["content"].encode("utf-8")).hexdigest()
    assert independent == v["computed_hash"]


@pytest.mark.asyncio
async def test_verify_unknown_brief_is_404(client):
    resp = await client.get(f"/briefs/{uuid4()}/verify")
    assert resp.status_code == 404
