"""Brief credentialing: tamper-evident SHA-256. Requires Postgres."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

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
async def test_brief_carries_verifiable_sha256(client, db_session):
    body = await _make_brief(client, db_session)

    digest = body["content_hash"]
    assert digest.startswith("sha256:")
    # The credential must be reproducible from the content alone.
    recomputed = "sha256:" + hashlib.sha256(body["content"].encode("utf-8")).hexdigest()
    assert digest == recomputed


@pytest.mark.asyncio
async def test_credential_is_stable_across_fetch(client, db_session):
    body = await _make_brief(client, db_session)
    again = await client.get(f"/briefs/{body['id']}")
    assert again.status_code == 200
    assert again.json()["content_hash"] == body["content_hash"]


@pytest.mark.asyncio
async def test_view_page_shows_credential(client, db_session):
    body = await _make_brief(client, db_session)
    view = await client.get(f"/briefs/{body['id']}/view")
    assert view.status_code == 200
    html = view.text
    assert "Credential" in html
    assert body["content_hash"] in html


@pytest.mark.asyncio
async def test_tampering_breaks_the_credential(client, db_session):
    body = await _make_brief(client, db_session)
    tampered = body["content"] + " (edited)"
    bad = "sha256:" + hashlib.sha256(tampered.encode("utf-8")).hexdigest()
    assert bad != body["content_hash"]
