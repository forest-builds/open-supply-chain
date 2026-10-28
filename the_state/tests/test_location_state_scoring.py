"""Pure scoring tests for LocationState. No DB required."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from state_products.location_state.place import parse_place
from state_products.location_state.schema import OperationalState
from state_products.location_state.scoring import (
    ScoredSignal,
    band_for_score,
    contribution_for,
    score_signals,
)


def _signal(signal_type: str, severity: str | None, contribution: float | None = None) -> dict:
    return {
        "signal_id": uuid4(),
        "signal_type": signal_type,
        "severity": severity,
        "source": "test",
        "raw_record_id": None,
        "title": f"{signal_type} {severity}",
        "occurred_at": datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        **({"contribution": contribution} if contribution is not None else {}),
    }


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.0, OperationalState.NORMAL),
        (0.24, OperationalState.NORMAL),
        (0.25, OperationalState.ELEVATED),
        (0.49, OperationalState.ELEVATED),
        (0.50, OperationalState.WATCH),
        (0.74, OperationalState.WATCH),
        (0.75, OperationalState.DISRUPTED),
        (0.89, OperationalState.DISRUPTED),
        (0.90, OperationalState.CRITICAL),
        (1.0, OperationalState.CRITICAL),
    ],
)
def test_band_for_score_boundaries(score, expected):
    assert band_for_score(score) == expected


@pytest.mark.parametrize(
    "signal_type,severity,expected",
    [
        ("weather_alert", "Extreme", 0.30),
        ("weather_alert", "Severe", 0.20),
        ("weather_alert", "Moderate", 0.10),
        ("weather_alert", "Minor", 0.04),
        ("weather_alert", "Unknown", 0.02),
        ("weather_alert", None, 0.02),
        ("declaration", "Major Disaster", 0.40),
        ("declaration", "Emergency", 0.25),
        ("civic_complaint", "High", 0.10),
        ("street_closure", "Medium", 0.10),
        ("public_event", "Low", 0.03),
        ("housing_violation", "High", 0.12),
        ("unknown_type", "Severe", 0.0),
        ("declaration", "garbage", 0.0),
    ],
)
def test_contribution_for(signal_type, severity, expected):
    assert contribution_for(signal_type, severity) == expected


def test_score_signals_empty_is_normal():
    result = score_signals([])
    assert result.risk_score == 0.0
    assert result.operational_state == OperationalState.NORMAL
    assert result.confidence == 0.0
    assert result.scored_signals == []


def test_score_signals_single_severe_weather_is_normal():
    # One Severe weather alert = 0.20 -> still NORMAL (band starts at 0.25).
    result = score_signals([_signal("weather_alert", "Severe")])
    assert result.risk_score == pytest.approx(0.20)
    assert result.operational_state == OperationalState.NORMAL


def test_score_signals_two_severe_weather_is_elevated():
    result = score_signals(
        [
            _signal("weather_alert", "Severe"),
            _signal("weather_alert", "Severe"),
        ]
    )
    assert result.risk_score == pytest.approx(0.40)
    assert result.operational_state == OperationalState.ELEVATED


def test_score_signals_one_major_disaster_is_elevated():
    result = score_signals([_signal("declaration", "Major Disaster")])
    assert result.risk_score == pytest.approx(0.40)
    assert result.operational_state == OperationalState.ELEVATED


def test_score_signals_mixed_can_reach_watch():
    result = score_signals(
        [
            _signal("declaration", "Major Disaster"),  # 0.40
            _signal("weather_alert", "Extreme"),  # 0.30
        ]
    )
    assert result.risk_score == pytest.approx(0.70)
    assert result.operational_state == OperationalState.WATCH


def test_score_signals_caps_at_one():
    signals = [_signal("declaration", "Major Disaster") for _ in range(5)]  # 5 * 0.40
    result = score_signals(signals)
    assert result.risk_score == 1.0
    assert result.operational_state == OperationalState.CRITICAL


def test_score_signals_ignores_unknown_contributions():
    # Unknown signal type contributes 0.0 and is excluded from scored list.
    result = score_signals(
        [
            _signal("weather_alert", "Severe"),
            _signal("garbage_type", "Severe"),
        ]
    )
    assert result.risk_score == pytest.approx(0.20)
    assert len(result.scored_signals) == 1


def _signal_from(source: str, occurred_at: datetime) -> dict:
    return {
        "signal_id": uuid4(),
        "signal_type": "weather_alert",
        "severity": "Severe",
        "source": source,
        "raw_record_id": None,
        "title": "t",
        "occurred_at": occurred_at,
    }


def test_confidence_zero_when_no_scored_signals():
    assert score_signals([]).confidence == 0.0
    # Unknown signals contribute nothing and must not inflate confidence.
    assert score_signals([_signal("garbage", "Severe")]).confidence == 0.0


def test_confidence_rewards_source_diversity_over_volume():
    now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    same_source = score_signals([_signal_from("noaa", now) for _ in range(5)], now=now)
    three_independent = score_signals(
        [
            _signal_from("nyc-311", now),
            _signal_from("nyc-dot", now),
            _signal_from("noaa", now),
        ],
        now=now,
    )
    assert three_independent.confidence > same_source.confidence


def test_confidence_rewards_recency():
    now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    fresh = score_signals(
        [_signal_from("noaa", now - timedelta(hours=1))],
        now=now,
        time_window_hours=24,
    )
    stale = score_signals(
        [_signal_from("noaa", now - timedelta(hours=22))],
        now=now,
        time_window_hours=24,
    )
    assert fresh.confidence > stale.confidence


def test_confidence_uses_calibration_data():
    now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    key = ("weather_alert", "severe")
    trusted = score_signals([_signal_from("noaa", now)], now=now, calibration_data={key: 0.9})
    distrusted = score_signals([_signal_from("noaa", now)], now=now, calibration_data={key: 0.1})
    assert trusted.confidence > distrusted.confidence


def test_confidence_is_mean_of_three_components():
    now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    result = score_signals(
        [
            _signal_from("a", now),
            _signal_from("b", now),
            _signal_from("c", now),
        ],
        now=now,
        time_window_hours=24,
        calibration_data={("weather_alert", "severe"): 0.6},
    )
    # source_diversity = 3/max(3,3) = 1.0; recency = 1.0 (age 0);
    # calibration = 0.6  -> mean = 0.8667
    assert result.confidence == pytest.approx(0.8667, abs=1e-4)


def test_weight_overrides_take_precedence():
    base = score_signals([_signal("street_closure", "High")])
    overridden = score_signals(
        [_signal("street_closure", "High")],
        weight_overrides={("street_closure", "high"): 0.05},
    )
    assert base.risk_score == pytest.approx(0.18)
    assert overridden.risk_score == pytest.approx(0.05)


def test_weight_overrides_only_affect_matching_pairs():
    result = score_signals(
        [_signal("weather_alert", "Severe")],
        weight_overrides={("street_closure", "high"): 0.99},
    )
    assert result.risk_score == pytest.approx(0.20)


def test_score_signals_is_deterministic():
    fixed_id = uuid4()
    signal = {
        "signal_id": fixed_id,
        "signal_type": "weather_alert",
        "severity": "Severe",
        "source": "noaa",
        "raw_record_id": None,
        "title": "test",
        "occurred_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
    }
    a = score_signals([signal])
    b = score_signals([signal])
    assert a.risk_score == b.risk_score
    assert a.operational_state == b.operational_state
    assert a.confidence == b.confidence
    assert [s.signal_id for s in a.scored_signals] == [s.signal_id for s in b.scored_signals]


def test_score_signals_accepts_scored_signal_dataclass():
    item = ScoredSignal(
        signal_id=uuid4(),
        signal_type="weather_alert",
        severity="Extreme",
        source="noaa",
        raw_record_id=None,
        title=None,
        occurred_at=None,
        contribution=0.30,
    )
    result = score_signals([item])
    assert result.risk_score == pytest.approx(0.30)


# Place parsing


def test_parse_place_city_state():
    p = parse_place("New York, NY")
    assert p.locality == "New York"
    assert p.state_code == "NY"
    assert p.borough is None


def test_parse_place_nyc_alias():
    p = parse_place("NYC")
    assert p.locality == "New York"
    assert p.state_code == "NY"
    assert p.borough is None


def test_parse_place_nyc_borough():
    p = parse_place("Brooklyn, NYC")
    assert p.locality == "New York"
    assert p.state_code == "NY"
    assert p.borough == "BROOKLYN"


def test_parse_place_state_name_only():
    p = parse_place("California")
    assert p.state_code == "CA"
    assert p.locality is None


def test_parse_place_bare_state_code():
    p = parse_place("TX")
    assert p.state_code == "TX"
    assert p.locality is None


def test_parse_place_full_state_name_with_city():
    p = parse_place("Houston, Texas")
    assert p.locality == "Houston"
    assert p.state_code == "TX"


def test_parse_place_unknown():
    p = parse_place("Atlantis")
    assert p.state_code is None
    assert p.locality == "Atlantis"


def test_parse_place_empty():
    p = parse_place("")
    assert p.state_code is None
    assert p.locality is None
