"""Public Python SDK (Task 1.4).

Async tests run end-to-end against the in-process app (+ Postgres, via the
conftest fixtures). Sync tests use a MockTransport so the synchronous wrapper
is exercised without an event loop.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from models.feedback_log import FeedbackLog
from models.signal import Signal
from models.source import Source
from sqlalchemy import select
from the_state_sdk import (
    NotFoundError,
    RateLimitError,
    TheStateClient,
    TheStateSyncClient,
)


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


@pytest.mark.asyncio
async def test_async_sdk_end_to_end(client, db_session):
    await _seed(db_session)
    sdk = TheStateClient(http_client=client)

    state = await sdk.get_state("New York, NY")
    assert state.place == "New York, NY"
    assert state.operational_state == "watch"
    assert state.risk_score == pytest.approx(0.7)

    wl = await sdk.create_watchlist("ops", ["New York, NY"])
    assert wl.places == ["New York, NY"]

    eval_resp = await client.post(f"/watchlists/{wl.id}/evaluate")
    assert eval_resp.status_code == 200
    gen = await client.post("/briefs/generate", json={"watchlist_id": wl.id})
    brief_id = gen.json()["id"]

    brief = await sdk.get_brief(brief_id)
    assert brief.id == brief_id
    assert brief.url.endswith(f"/briefs/{brief_id}")

    await sdk.log_feedback(brief_id, false_positive=True)
    rows = (
        (await db_session.execute(select(FeedbackLog).where(FeedbackLog.brief_id == brief_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].false_positive is True


@pytest.mark.asyncio
async def test_async_sdk_raises_not_found(client):
    sdk = TheStateClient(http_client=client)
    with pytest.raises(NotFoundError):
        await sdk.get_brief("00000000-0000-0000-0000-000000000000")


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/state/location":
            assert request.url.params["place"] == "Brooklyn, NYC"
            return httpx.Response(
                200,
                json={
                    "place": "Brooklyn, NYC",
                    "time_window": "24h",
                    "operational_state": "elevated",
                    "risk_score": 0.4,
                    "summary": "ok",
                    "confidence": 0.5,
                    "computed_at": "2026-05-18T00:00:00Z",
                },
            )
        if request.url.path == "/feedback/":
            return httpx.Response(429, json={"detail": "slow down"})
        return httpx.Response(404, json={"detail": "nope"})

    return httpx.MockTransport(handler)


def test_sync_sdk_get_state_and_rate_limit():
    http = httpx.AsyncClient(transport=_mock_transport(), base_url="http://test")
    sdk = TheStateSyncClient(http_client=http)

    state = sdk.get_state("Brooklyn, NYC")
    assert state.operational_state == "elevated"
    assert state.risk_score == 0.4

    with pytest.raises(RateLimitError):
        sdk.log_feedback("brief-1", false_positive=True)

    sdk.close()
