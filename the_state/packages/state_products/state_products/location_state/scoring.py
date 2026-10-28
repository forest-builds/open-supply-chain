from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from statistics import fmean
from typing import Iterable
from uuid import UUID

from state_products.location_state.schema import OperationalState

# Deterministic scoring weights. Adjust here and update tests.
SCORING_WEIGHTS: dict[tuple[str, str], float] = {
    ("weather_alert", "extreme"): 0.30,
    ("weather_alert", "severe"): 0.20,
    ("weather_alert", "moderate"): 0.10,
    ("weather_alert", "minor"): 0.04,
    ("weather_alert", "unknown"): 0.02,
    ("declaration", "major disaster"): 0.40,
    ("declaration", "emergency"): 0.25,
    ("civic_complaint", "high"): 0.10,
    ("civic_complaint", "medium"): 0.06,
    ("civic_complaint", "low"): 0.02,
    ("street_closure", "high"): 0.18,
    ("street_closure", "medium"): 0.10,
    ("street_closure", "low"): 0.04,
    ("public_event", "medium"): 0.08,
    ("public_event", "low"): 0.03,
    ("housing_violation", "high"): 0.12,
    ("housing_violation", "medium"): 0.07,
    ("housing_violation", "low"): 0.03,
}

# Floor for the source-diversity denominator. A single dominant source should
# never read as full confidence just because it is the only source present.
_MIN_DIVERSITY_BASE = 3

# Neutral calibration score for a (signal_type, severity) pair with no
# feedback history. 0.5 is "no evidence either way".
_NEUTRAL_CALIBRATION = 0.5


@dataclass(frozen=True)
class ScoredSignal:
    signal_id: UUID
    signal_type: str
    severity: str | None
    source: str
    raw_record_id: UUID | None
    title: str | None
    occurred_at: datetime | None
    contribution: float


@dataclass(frozen=True)
class ScoringResult:
    risk_score: float
    operational_state: OperationalState
    confidence: float
    scored_signals: list[ScoredSignal]


def _pair_key(signal_type: str | None, severity: str | None) -> tuple[str, str]:
    return ((signal_type or "").lower(), (severity or "unknown").lower())


def contribution_for(
    signal_type: str,
    severity: str | None,
    weight_overrides: dict[tuple[str, str], float] | None = None,
) -> float:
    """Look up the deterministic weight for a (signal_type, severity) pair.

    Unknown combinations contribute 0.0. The lookup is case-insensitive on both
    keys so adapters do not need to normalize. When ``weight_overrides`` is
    provided, a matching pair takes precedence over ``SCORING_WEIGHTS`` — this
    is how feedback-calibrated weights replace the static guesses.
    """
    if signal_type is None:
        return 0.0
    key = _pair_key(signal_type, severity)
    if weight_overrides is not None and key in weight_overrides:
        return weight_overrides[key]
    return SCORING_WEIGHTS.get(key, 0.0)


def band_for_score(score: float) -> OperationalState:
    """Map a 0.0-1.0 score to its operational state band (deterministic)."""
    if score >= 0.90:
        return OperationalState.CRITICAL
    if score >= 0.75:
        return OperationalState.DISRUPTED
    if score >= 0.50:
        return OperationalState.WATCH
    if score >= 0.25:
        return OperationalState.ELEVATED
    return OperationalState.NORMAL


def score_signals(
    signals: Iterable[ScoredSignal | dict],
    *,
    weight_overrides: dict[tuple[str, str], float] | None = None,
    time_window_hours: float = 24.0,
    calibration_data: dict[tuple[str, str], float] | None = None,
    now: datetime | None = None,
) -> ScoringResult:
    """Pure scoring: take signal-shaped inputs, return score + band + confidence.

    Inputs may be ScoredSignal instances or dicts with the same keys. Dict form
    lets the service layer build inputs without importing this module's types.

    The scoring contract is unchanged: same signals produce the same
    ``risk_score`` and ``operational_state``. ``weight_overrides`` only swaps
    the per-pair weight (feedback calibration); ``calibration_data``/``now``/
    ``time_window_hours`` only feed the confidence model. The function is pure —
    it never reads the clock; callers pass ``now`` for recency.
    """
    scored: list[ScoredSignal] = []
    total = 0.0

    for raw in signals:
        item = _coerce(raw)
        if weight_overrides is not None:
            key = _pair_key(item.signal_type, item.severity)
            if key in weight_overrides:
                item = replace(item, contribution=weight_overrides[key])
        if item.contribution > 0:
            scored.append(item)
            total += item.contribution

    risk_score = min(1.0, total)
    confidence = _confidence(scored, time_window_hours, calibration_data, now)
    return ScoringResult(
        risk_score=risk_score,
        operational_state=band_for_score(risk_score),
        confidence=confidence,
        scored_signals=scored,
    )


def _confidence(
    scored: list[ScoredSignal],
    time_window_hours: float,
    calibration_data: dict[tuple[str, str], float] | None,
    now: datetime | None,
) -> float:
    """Confidence = mean(source_diversity, recency_score, calibration_score).

    Reflects how trustworthy the read is, not how many signals fired. Five
    signals from one source is weaker evidence than three from three
    independent sources; a stale signal is weaker than a fresh one.
    """
    if not scored:
        return 0.0

    unique_sources = len({s.source for s in scored})
    source_diversity = unique_sources / max(unique_sources, _MIN_DIVERSITY_BASE)

    recency_score = _recency_score(scored, time_window_hours, now)

    if calibration_data is None:
        calibration_score = _NEUTRAL_CALIBRATION
    else:
        calibration_score = fmean(
            calibration_data.get(_pair_key(s.signal_type, s.severity), _NEUTRAL_CALIBRATION)
            for s in scored
        )

    return round(fmean([source_diversity, recency_score, calibration_score]), 4)


def _recency_score(
    scored: list[ScoredSignal],
    time_window_hours: float,
    now: datetime | None,
) -> float:
    """Mean of per-signal freshness within the window: 1 at age 0, 0 at the edge.

    ``now`` anchors age. When the caller does not supply it (pure callers in
    tests), the most recent signal anchors the window. Signals with no
    timestamp contribute a neutral 0.5.
    """
    timestamps = [s.occurred_at for s in scored if s.occurred_at is not None]
    if now is None:
        if not timestamps:
            return _NEUTRAL_CALIBRATION
        now = max(_as_utc(ts) for ts in timestamps)

    window = max(time_window_hours, 1e-9)
    per_signal: list[float] = []
    for s in scored:
        if s.occurred_at is None:
            per_signal.append(_NEUTRAL_CALIBRATION)
            continue
        age_hours = (now - _as_utc(s.occurred_at)).total_seconds() / 3600.0
        per_signal.append(_clamp(1.0 - age_hours / window))
    return fmean(per_signal)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _coerce(raw: ScoredSignal | dict) -> ScoredSignal:
    if isinstance(raw, ScoredSignal):
        return raw
    signal_type = raw.get("signal_type", "")
    severity = raw.get("severity")
    contribution = raw.get("contribution")
    if contribution is None:
        contribution = contribution_for(signal_type, severity)
    return ScoredSignal(
        signal_id=raw["signal_id"],
        signal_type=signal_type,
        severity=severity,
        source=raw.get("source", "unknown"),
        raw_record_id=raw.get("raw_record_id"),
        title=raw.get("title"),
        occurred_at=raw.get("occurred_at"),
        contribution=contribution,
    )
