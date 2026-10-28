from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from fastapi import HTTPException
from models.signal import Signal
from models.source import Source
from models.state_snapshot import StateSnapshot
from schemas.state import LocationStateHistoryEntry
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from state_products.location_state.place import Place, parse_place
from state_products.location_state.schema import (
    ActiveSignal,
    Driver,
    LocationState,
    Provenance,
    RecentChange,
    Recommendation,
    SubLocationState,
)
from state_products.location_state.scoring import (
    ScoredSignal,
    contribution_for,
    score_signals,
)

from services.scoring_calibration_service import load_calibration

# Deterministic recommendation templates by state band. No LLM here.
_RECOMMENDATIONS: dict[str, list[Recommendation]] = {
    "normal": [
        Recommendation(action="Continue normal operations"),
    ],
    "elevated": [
        Recommendation(action="Monitor signals for state escalation"),
        Recommendation(action="Review on-call coverage"),
    ],
    "watch": [
        Recommendation(action="Brief stakeholders on the current state"),
        Recommendation(action="Prepare contingency plans"),
        Recommendation(action="Increase signal monitoring cadence"),
    ],
    "disrupted": [
        Recommendation(action="Activate response procedures"),
        Recommendation(action="Notify affected parties"),
        Recommendation(action="Stand up incident channels"),
    ],
    "critical": [
        Recommendation(action="Execute emergency protocols"),
        Recommendation(action="Coordinate with relevant authorities"),
        Recommendation(action="Escalate to leadership"),
    ],
}

_DRIVER_LABELS: dict[str, str] = {
    "weather_alert": "Weather alerts",
    "declaration": "Federal disaster declarations",
    "civic_complaint": "311 civic complaints",
    "street_closure": "Street closures",
    "public_event": "Public events",
    "housing_violation": "Housing violations",
}

_TIME_WINDOW_RE = re.compile(r"^\s*(\d+)\s*([hdwm])\s*$", re.IGNORECASE)


class LocationStateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_location_state(
        self,
        *,
        place: str,
        time_window: str = "24h",
    ) -> LocationState:
        parsed = parse_place(place)
        if parsed.state_code is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Could not resolve a US state from place. "
                    "Try '<City>, <STATE>' or a full state name."
                ),
            )

        window = _parse_time_window(time_window)
        now = datetime.now(timezone.utc)
        since = now - window
        time_window_hours = window.total_seconds() / 3600.0

        weight_overrides, calibration_data = await load_calibration(self.db)

        signals_with_source = await self._load_signals(parsed, since)
        scored = [
            _to_scored_signal(signal, source_name, weight_overrides)
            for signal, source_name in signals_with_source
        ]
        location_by_id = {signal.id: _signal_location(signal) for signal, _ in signals_with_source}
        scoring_kwargs = {
            "weight_overrides": weight_overrides,
            "time_window_hours": time_window_hours,
            "calibration_data": calibration_data,
            "now": now,
        }
        result = score_signals(scored, **scoring_kwargs)
        sub_locations = _build_sub_locations(
            parsed, result.scored_signals, location_by_id, scoring_kwargs
        )

        state = LocationState(
            place=parsed.raw,
            state_code=parsed.state_code,
            time_window=time_window,
            operational_state=result.operational_state,
            risk_score=round(result.risk_score, 4),
            summary=_summary(parsed, result.operational_state, len(result.scored_signals)),
            drivers=_build_drivers(result.scored_signals),
            active_signals=[
                ActiveSignal(
                    signal_id=s.signal_id,
                    signal_type=s.signal_type,
                    source=s.source,
                    severity=s.severity,
                    title=s.title,
                    occurred_at=s.occurred_at,
                    contribution=s.contribution,
                )
                for s in result.scored_signals
            ],
            recent_changes=_build_recent_changes(result.scored_signals),
            recommended_actions=_RECOMMENDATIONS[result.operational_state.value],
            confidence=round(result.confidence, 4),
            provenance=[
                Provenance(
                    signal_id=s.signal_id,
                    source=s.source,
                    raw_record_id=s.raw_record_id,
                    contribution=s.contribution,
                    observed_at=s.occurred_at,
                )
                for s in result.scored_signals
            ],
            sub_locations=sub_locations,
            computed_at=now,
        )
        # Append-only memory: every state read leaves an immutable snapshot.
        # Flush (not commit) so this stays atomic inside a caller's
        # transaction (e.g. watchlist evaluation); the route layer commits.
        self.db.add(
            StateSnapshot(
                snapshot_type="location_state",
                summary=state.summary,
                state=state.model_dump(mode="json"),
                computed_from={
                    "place": parsed.raw,
                    "place_key": _place_key(parsed),
                    "time_window": time_window,
                    "signal_ids": [str(s.signal_id) for s in result.scored_signals],
                    "computed_by": "LocationStateService",
                },
                computed_at=now,
            )
        )
        await self.db.flush()
        return state

    async def get_location_state_history(
        self,
        *,
        place: str,
        from_dt: datetime,
        to_dt: datetime,
        limit: int = 48,
    ) -> list[LocationStateHistoryEntry]:
        parsed = parse_place(place)
        if parsed.state_code is None:
            raise HTTPException(status_code=400, detail="Unresolvable place")
        stmt = (
            select(StateSnapshot)
            .where(StateSnapshot.snapshot_type == "location_state")
            .where(StateSnapshot.computed_from["place_key"].astext == _place_key(parsed))
            .where(StateSnapshot.computed_at >= from_dt)
            .where(StateSnapshot.computed_at <= to_dt)
            .order_by(StateSnapshot.computed_at.desc())
            .limit(max(1, min(limit, 500)))
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        entries: list[LocationStateHistoryEntry] = []
        for snap in rows:
            blob = snap.state or {}
            entries.append(
                LocationStateHistoryEntry(
                    computed_at=snap.computed_at,
                    operational_state=str(blob.get("operational_state", "normal")),
                    risk_score=float(blob.get("risk_score", 0.0)),
                    confidence=float(blob.get("confidence", 0.0)),
                    signal_count=len(blob.get("active_signals", []) or []),
                )
            )
        return entries

    async def _load_signals(self, place: Place, since: datetime) -> list[tuple[Signal, str]]:
        # Match signals whose JSONB location.state equals the state code.
        # Adapters can also store state in attributes for FEMA-style records.
        location_match = Signal.location["state"].astext == place.state_code
        attributes_match = Signal.attributes["state"].astext == place.state_code

        location_filter = or_(location_match, attributes_match)
        if place.borough is not None:
            borough_match = or_(
                Signal.location["borough"].astext == place.borough,
                Signal.attributes["borough"].astext == place.borough,
            )
            location_filter = and_(location_filter, borough_match)

        stmt = (
            select(Signal, Source.name)
            .join(Source, Source.id == Signal.source_id)
            .where(location_filter)
            .where(Signal.observed_at >= since)
            .order_by(Signal.observed_at.desc())
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


def _place_key(place: Place) -> str:
    """Stable history key: same place resolves the same regardless of the
    exact raw string the caller typed (state + optional borough)."""
    return f"{place.state_code}|{place.borough or ''}"


def _parse_time_window(value: str) -> timedelta:
    match = _TIME_WINDOW_RE.match(value or "")
    if not match:
        raise HTTPException(
            status_code=400,
            detail="time_window must look like '24h', '7d', '2w', or '1m'",
        )
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if amount <= 0:
        raise HTTPException(status_code=400, detail="time_window must be positive")
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "w":
        return timedelta(weeks=amount)
    # 'm' = 30 days; calendar months are out of scope for v0.
    return timedelta(days=30 * amount)


def _to_scored_signal(
    signal: Signal,
    source_name: str,
    weight_overrides: dict[tuple[str, str], float] | None = None,
) -> ScoredSignal:
    contribution = contribution_for(signal.signal_type, signal.severity, weight_overrides)
    return ScoredSignal(
        signal_id=signal.id,
        signal_type=signal.signal_type,
        severity=signal.severity,
        source=source_name,
        raw_record_id=signal.raw_record_id,
        title=signal.title,
        occurred_at=signal.occurred_at or signal.observed_at,
        contribution=contribution,
    )


def _build_drivers(scored: Iterable[ScoredSignal]) -> list[Driver]:
    grouped: dict[str, list[ScoredSignal]] = defaultdict(list)
    for s in scored:
        grouped[s.signal_type].append(s)
    drivers: list[Driver] = []
    for signal_type, items in grouped.items():
        weight = min(1.0, sum(i.contribution for i in items))
        drivers.append(
            Driver(
                label=_DRIVER_LABELS.get(signal_type, signal_type.replace("_", " ").title()),
                weight=round(weight, 4),
                signal_ids=[i.signal_id for i in items],
            )
        )
    drivers.sort(key=lambda d: d.weight, reverse=True)
    return drivers


def _build_recent_changes(scored: Iterable[ScoredSignal]) -> list[RecentChange]:
    # Top 5 most recent contributors, treated as the "recent changes" stream.
    items = [s for s in scored if s.occurred_at is not None]
    items.sort(key=lambda s: s.occurred_at, reverse=True)  # type: ignore[arg-type, return-value]
    return [
        RecentChange(
            occurred_at=s.occurred_at,  # type: ignore[arg-type]
            description=s.title or f"{s.signal_type} ({s.severity or 'unknown'})",
            signal_id=s.signal_id,
        )
        for s in items[:5]
    ]


def _signal_location(signal: Signal) -> dict[str, str]:
    """Pull sub-location keys (borough/zip/nta) off a signal's JSONB blobs."""
    out: dict[str, str] = {}
    for blob in (signal.location, signal.attributes):
        if not blob:
            continue
        for key in ("borough", "zip", "nta"):
            value = blob.get(key)
            if value and key not in out:
                out[key] = str(value)
    return out


def _build_sub_locations(
    place: Place,
    scored: list[ScoredSignal],
    location_by_id: dict,  # noqa: ANN001 - UUID -> dict[str, str]
    scoring_kwargs: dict,  # noqa: ANN001
) -> list[SubLocationState]:
    """Break the rolled-up state down one level of geographic granularity.

    City -> per-borough. Borough -> per-ZIP, else per-NTA. Each bucket is
    rescored with the exact same ``score_signals`` call as the parent — no
    second scoring path, so the breakdown can never disagree with the rollup.
    """
    if place.borough is not None:
        granularity = "zip"
        key = "zip"
        if not any("zip" in location_by_id.get(s.signal_id, {}) for s in scored):
            granularity = key = "nta"
    elif place.locality is not None:
        granularity = key = "borough"
    else:
        return []

    buckets: dict[str, list[ScoredSignal]] = defaultdict(list)
    for s in scored:
        name = location_by_id.get(s.signal_id, {}).get(key)
        if name:
            buckets[name].append(s)

    sub: list[SubLocationState] = []
    for name, items in buckets.items():
        result = score_signals(items, **scoring_kwargs)
        sub.append(
            SubLocationState(
                name=name,
                granularity=granularity,
                operational_state=result.operational_state,
                risk_score=round(result.risk_score, 4),
                signal_count=len(result.scored_signals),
            )
        )
    sub.sort(key=lambda x: (-x.risk_score, x.name))
    return sub


def _summary(place: Place, state, signal_count: int) -> str:  # noqa: ANN001
    label = place.raw.strip() or (place.state_code or "")
    if signal_count == 0:
        return f"No active disruption signals for {label} in the requested window."
    plural = "signals" if signal_count != 1 else "signal"
    return (
        f"{label} is in {state.value} state with {signal_count} active "
        f"{plural} in the requested window."
    )
