"""Feedback-driven scoring calibration (Task 0.1). Requires Postgres."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models.brief import Brief
from models.feedback_log import FeedbackLog
from models.signal import Signal
from models.source import Source
from models.state_evaluation_result import StateEvaluationResult
from models.watched_entity import WatchedEntity
from models.watchlist import Watchlist
from services.scoring_calibration_service import (
    calibrated_weights,
    refresh_weight_cache,
)

PAIR = ("street_closure", "high")
BASE_WEIGHT = 0.18


async def _seed_feedback(
    db,
    *,
    false_positive: bool = False,
    outcome: str | None = None,
    count: int = 1,
) -> None:
    source = Source(name="nyc-dot", source_type="nyc-dot")
    db.add(source)
    await db.flush()
    signal = Signal(
        source_id=source.id,
        signal_type="street_closure",
        severity="High",
        title="closure",
        observed_at=datetime.now(timezone.utc),
        occurred_at=datetime.now(timezone.utc),
        location={"state": "NY"},
        attributes={},
    )
    db.add(signal)
    await db.flush()

    watchlist = Watchlist(name="wl", evaluation_cadence="24h", meta={})
    db.add(watchlist)
    await db.flush()
    entity = WatchedEntity(
        watchlist_id=watchlist.id,
        entity_type="location",
        entity_ref="Brooklyn, NYC",
    )
    db.add(entity)
    await db.flush()

    for _ in range(count):
        result = StateEvaluationResult(
            watched_entity_id=entity.id,
            evaluated_at=datetime.now(timezone.utc),
            current_state="elevated",
            current_score=0.18,
            confidence=0.5,
            provenance=[{"signal_id": str(signal.id), "source": "nyc-dot"}],
        )
        db.add(result)
        await db.flush()
        brief = Brief(
            watched_entity_id=entity.id,
            evaluation_result_id=result.id,
            content="x",
        )
        db.add(brief)
        await db.flush()
        db.add(
            FeedbackLog(
                brief_id=brief.id,
                watched_entity_id=entity.id,
                false_positive=false_positive,
                outcome=outcome,
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_false_positive_decays_weight(db_session):
    await _seed_feedback(db_session, false_positive=True)
    weights = await calibrated_weights(db_session)
    assert PAIR in weights
    assert weights[PAIR] < BASE_WEIGHT


@pytest.mark.asyncio
async def test_confirmed_disruption_compounds_weight(db_session):
    await _seed_feedback(db_session, outcome="disruption_confirmed")
    weights = await calibrated_weights(db_session)
    assert PAIR in weights
    assert weights[PAIR] > BASE_WEIGHT


@pytest.mark.asyncio
async def test_falls_back_to_static_when_no_feedback(db_session):
    assert await calibrated_weights(db_session) == {}


@pytest.mark.asyncio
async def test_cache_is_populated_and_reused(db_session):
    await _seed_feedback(db_session, false_positive=True, count=2)
    await refresh_weight_cache(db_session)
    weights = await calibrated_weights(db_session)
    assert weights[PAIR] < BASE_WEIGHT


@pytest.mark.asyncio
async def test_state_location_uses_calibrated_weights(client, db_session):
    # Two confirmed disruptions for (street_closure, high) lift the weight,
    # so the same single signal yields a higher risk_score than the static 0.18.
    await _seed_feedback(db_session, outcome="disruption_confirmed", count=3)

    src = Source(name="nyc-dot-live", source_type="nyc-dot")
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    sig = Signal(
        source_id=src.id,
        signal_type="street_closure",
        severity="High",
        title="live closure",
        observed_at=datetime.now(timezone.utc),
        occurred_at=datetime.now(timezone.utc),
        location={"state": "NY"},
        attributes={},
    )
    db_session.add(sig)
    await db_session.commit()

    resp = await client.get("/state/location", params={"place": "New York, NY"})
    assert resp.status_code == 200
    assert resp.json()["risk_score"] > BASE_WEIGHT
