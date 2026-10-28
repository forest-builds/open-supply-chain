"""Deterministic operational decision (pure) + the /decisions/check API."""

from __future__ import annotations

import pytest
from state_products.location_state.decision import decide
from state_products.location_state.schema import OperationalState


def test_band_maps_to_decision():
    cases = {
        OperationalState.NORMAL: "proceed",
        OperationalState.ELEVATED: "proceed_with_caution",
        OperationalState.WATCH: "hold",
        OperationalState.DISRUPTED: "hold",
        OperationalState.CRITICAL: "escalate",
    }
    for state, expected in cases.items():
        d = decide(
            operational_state=state,
            risk_score=0.4,
            confidence=0.8,
            time_window="next_4_hours",
        )
        assert d.decision == expected
        assert d.confidence == "high"


def test_risk_tolerance_shifts_one_rung_each_way():
    low = decide(
        operational_state=OperationalState.NORMAL,
        risk_score=0.1,
        confidence=0.5,
        time_window="x",
        risk_tolerance="low",
    )
    high = decide(
        operational_state=OperationalState.ELEVATED,
        risk_score=0.3,
        confidence=0.5,
        time_window="x",
        risk_tolerance="high",
    )
    assert low.decision == "proceed_with_caution"  # bumped up from proceed
    assert high.decision == "proceed"  # relaxed down from caution


def test_relaxation_never_drops_real_disruption_below_hold():
    d = decide(
        operational_state=OperationalState.DISRUPTED,
        risk_score=0.8,
        confidence=0.9,
        time_window="x",
        risk_tolerance="high",
    )
    assert d.decision == "hold"


def test_determinism_and_score_scaling():
    a = decide(
        operational_state=OperationalState.WATCH,
        risk_score=0.55,
        confidence=0.4,
        time_window="x",
    )
    b = decide(
        operational_state=OperationalState.WATCH,
        risk_score=0.55,
        confidence=0.4,
        time_window="x",
    )
    assert a == b
    assert a.disruption_score == 55
    assert a.confidence == "medium"
    assert a.safe_for_automation == "no"


@pytest.mark.asyncio
async def test_decisions_check_endpoint_is_grounded(client):
    resp = await client.post(
        "/decisions/check",
        json={
            "location": "New York, NY",
            "operation_type": "field_dispatch",
            "time_window": "next_4_hours",
            "risk_tolerance": "normal",
        },
    )
    assert resp.status_code == 200
    b = resp.json()
    assert b["decision"] in {"proceed", "proceed_with_caution", "hold", "escalate"}
    assert b["location"] == "New York, NY"
    assert b["coverage_level"] == "limited"
    # Honest coverage: connected sources listed, others explicitly excluded.
    assert "nyc_311" in b["included_sources"]
    assert "weather_alerts" in b["excluded_sources"]
    assert "currently connected public records" in b["coverage_warning"]


@pytest.mark.asyncio
async def test_decisions_check_rejects_unresolvable_place(client):
    resp = await client.post("/decisions/check", json={"location": "Atlantis"})
    assert resp.status_code == 400
