"""Brief routes. Requires Postgres (see conftest.py)."""

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


async def _create_evaluated_watchlist(client, db_session) -> tuple[str, str]:
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
    assert create_resp.status_code == 201
    watchlist_id = create_resp.json()["id"]

    eval_resp = await client.post(f"/watchlists/{watchlist_id}/evaluate")
    assert eval_resp.status_code == 200
    return watchlist_id, eval_resp.json()["id"]


@pytest.mark.asyncio
async def test_generate_and_get_brief_from_watchlist(client, db_session):
    watchlist_id, evaluation_result_id = await _create_evaluated_watchlist(
        client,
        db_session,
    )

    generate_resp = await client.post(
        "/briefs/generate",
        json={"watchlist_id": watchlist_id},
    )

    assert generate_resp.status_code == 201
    body = generate_resp.json()
    assert body["watched_entity_id"]
    assert body["evaluation_result_id"] == evaluation_result_id
    assert body["title"] == "New York, NY Operational Brief"
    assert body["place"] == "New York, NY"
    assert body["operational_state"] == "watch"
    assert body["risk_score"] == pytest.approx(0.7)
    assert body["summary"].startswith("New York, NY is watch")
    assert body["what_changed"] == "This is the first stored evaluation for the watched location."
    assert "readiness steps" in body["why_it_matters"]
    assert len(body["recommended_actions"]) >= 1
    assert len(body["evidence"]) == 2
    assert body["content"].startswith("# Operational Brief - New York, NY")
    assert body["url"] == f"http://test/briefs/{body['id']}"

    get_resp = await client.get(f"/briefs/{body['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == body


@pytest.mark.asyncio
async def test_generate_brief_from_evaluation_result(client, db_session):
    _, evaluation_result_id = await _create_evaluated_watchlist(client, db_session)

    generate_resp = await client.post(
        "/briefs/generate",
        json={"evaluation_result_id": evaluation_result_id},
    )

    assert generate_resp.status_code == 201
    assert generate_resp.json()["evaluation_result_id"] == evaluation_result_id


@pytest.mark.asyncio
async def test_generate_brief_requires_prior_evaluation(client):
    create_resp = await client.post(
        "/watchlists/",
        json={"name": "NYC Morning Ops", "place": "New York, NY"},
    )
    watchlist_id = create_resp.json()["id"]

    generate_resp = await client.post(
        "/briefs/generate",
        json={"watchlist_id": watchlist_id},
    )

    assert generate_resp.status_code == 409
    assert generate_resp.json()["detail"] == (
        "No evaluation result found; evaluate the watchlist first"
    )


@pytest.mark.asyncio
async def test_brief_not_found(client):
    resp = await client.get(f"/briefs/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_brief_view_renders_public_html(client, db_session):
    watchlist_id, _ = await _create_evaluated_watchlist(client, db_session)
    generate_resp = await client.post("/briefs/generate", json={"watchlist_id": watchlist_id})
    assert generate_resp.status_code == 201
    brief_id = generate_resp.json()["id"]

    view_resp = await client.get(f"/briefs/{brief_id}/view")

    assert view_resp.status_code == 200
    assert view_resp.headers["content-type"].startswith("text/html")
    html = view_resp.text
    assert "<!doctype html>" in html
    assert "watch" in html  # operational state
    assert "Risk score" in html
    assert "Provenance chain" in html
    assert "Active signals" in html
    assert "Evaluated at" in html  # timestamp
    # Raw JSON cross-link present, no auth wall.
    assert f"/briefs/{brief_id}" in html


@pytest.mark.asyncio
async def test_brief_view_not_found(client):
    resp = await client.get(f"/briefs/{uuid4()}/view")
    assert resp.status_code == 404
