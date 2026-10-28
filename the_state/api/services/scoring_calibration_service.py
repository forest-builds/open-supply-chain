"""Feedback-driven calibration of the deterministic scoring weights.

This is the flywheel. ``FeedbackLog`` rows carry ``false_positive`` and
``outcome`` signals that, until now, nothing read. We trace each feedback
record back through the brief it concerns to the signals that drove that
brief's state, then Bayesian-update the weight for every
``(signal_type, severity)`` pair involved:

    FeedbackLog -> Brief -> StateEvaluationResult.provenance -> Signal

A confirmed disruption compounds a pair's weight; a false positive decays it.
With no feedback for a pair, calibration is silent and ``SCORING_WEIGHTS``
stands. Aggregates are materialized into ``scoring_weight_cache`` so a request
never scans the full feedback table.
"""

from __future__ import annotations

import uuid

from models.brief import Brief
from models.feedback_log import FeedbackLog
from models.scoring_weight_cache import ScoringWeightCache
from models.signal import Signal
from models.state_evaluation_result import StateEvaluationResult
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from state_products.location_state.scoring import SCORING_WEIGHTS

# An outcome that confirms the state read was real (compounds weight).
_CONFIRMED_OUTCOMES = frozenset({"disruption_confirmed"})

# Beta(1, 1): a uniform prior whose mean is 0.5 ("no evidence either way").
# Confirmed disruptions are successes, false positives are failures. The
# posterior mean is the calibrated reliability of the pair.
_PRIOR_ALPHA = 1.0
_PRIOR_BETA = 1.0
_PRIOR_MEAN = _PRIOR_ALPHA / (_PRIOR_ALPHA + _PRIOR_BETA)


def _pair_key(signal_type: str | None, severity: str | None) -> tuple[str, str]:
    return ((signal_type or "").lower(), (severity or "unknown").lower())


def _posterior_mean(false_positives: int, confirmed: int) -> float:
    alpha = _PRIOR_ALPHA + confirmed
    beta = _PRIOR_BETA + false_positives
    return alpha / (alpha + beta)


def _calibrated_weight(pair: tuple[str, str], posterior: float) -> float:
    base = SCORING_WEIGHTS.get(pair, 0.0)
    # Scale the static weight by reliability relative to the neutral prior:
    # posterior > 0.5 compounds, < 0.5 decays. Clamped to the [0, 1] contract.
    return max(0.0, min(1.0, base * posterior / _PRIOR_MEAN))


async def _aggregate_feedback(db: AsyncSession) -> dict[tuple[str, str], tuple[int, int]]:
    """Return ``{(signal_type, severity): (false_positives, confirmed)}``."""
    stmt = (
        select(FeedbackLog, StateEvaluationResult.provenance)
        .join(Brief, Brief.id == FeedbackLog.brief_id)
        .join(
            StateEvaluationResult,
            StateEvaluationResult.id == Brief.evaluation_result_id,
        )
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return {}

    records: list[tuple[bool, bool, set[uuid.UUID]]] = []
    all_ids: set[uuid.UUID] = set()
    for feedback, provenance in rows:
        ids: set[uuid.UUID] = set()
        for entry in provenance or []:
            raw_id = entry.get("signal_id")
            if not raw_id:
                continue
            try:
                ids.add(uuid.UUID(str(raw_id)))
            except (ValueError, AttributeError):
                continue
        all_ids |= ids
        records.append(
            (
                bool(feedback.false_positive),
                feedback.outcome in _CONFIRMED_OUTCOMES,
                ids,
            )
        )

    if not all_ids:
        return {}

    sig_rows = (
        await db.execute(
            select(Signal.id, Signal.signal_type, Signal.severity).where(Signal.id.in_(all_ids))
        )
    ).all()
    id_to_pair = {sid: _pair_key(signal_type, severity) for sid, signal_type, severity in sig_rows}

    agg: dict[tuple[str, str], list[int]] = {}
    for false_positive, confirmed, ids in records:
        # One feedback record speaks to every pair that drove its brief.
        pairs = {id_to_pair[sid] for sid in ids if sid in id_to_pair}
        for pair in pairs:
            counts = agg.setdefault(pair, [0, 0])
            if false_positive:
                counts[0] += 1
            if confirmed:
                counts[1] += 1
    return {pair: (c[0], c[1]) for pair, c in agg.items()}


async def refresh_weight_cache(db: AsyncSession) -> None:
    """Recompute calibration from FeedbackLog and replace the cache table.

    Cheap enough to call after a feedback write or on a schedule.
    """
    agg = await _aggregate_feedback(db)
    await db.execute(delete(ScoringWeightCache))
    for pair, (false_positives, confirmed) in agg.items():
        posterior = _posterior_mean(false_positives, confirmed)
        db.add(
            ScoringWeightCache(
                signal_type=pair[0],
                severity=pair[1],
                weight=_calibrated_weight(pair, posterior),
                accuracy=posterior,
                false_positive_count=false_positives,
                confirmed_count=confirmed,
            )
        )
    await db.commit()


async def _cache_rows(db: AsyncSession) -> list[ScoringWeightCache]:
    rows = list((await db.execute(select(ScoringWeightCache))).scalars().all())
    if rows:
        return rows
    # Cold cache: populate lazily. With no feedback the joins are empty and
    # this stays cheap; SCORING_WEIGHTS then stands unmodified.
    if not await _aggregate_feedback(db):
        return []
    await refresh_weight_cache(db)
    return list((await db.execute(select(ScoringWeightCache))).scalars().all())


async def load_calibration(
    db: AsyncSession,
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    """Single read of (weight_overrides, calibration_scores) for the scorer."""
    rows = await _cache_rows(db)
    weights = {(r.signal_type, r.severity): r.weight for r in rows}
    scores = {(r.signal_type, r.severity): r.accuracy for r in rows}
    return weights, scores


async def calibrated_weights(db: AsyncSession) -> dict[tuple[str, str], float]:
    """Feedback-adjusted weight map. Empty when no feedback exists yet."""
    weights, _ = await load_calibration(db)
    return weights


async def calibration_scores(db: AsyncSession) -> dict[tuple[str, str], float]:
    """Per-pair reliability in [0, 1] for the confidence calibration term."""
    _, scores = await load_calibration(db)
    return scores
