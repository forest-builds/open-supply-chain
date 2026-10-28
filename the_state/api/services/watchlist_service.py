from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from models.state_evaluation_result import StateEvaluationResult
from models.watched_entity import WatchedEntity
from models.watchlist import Watchlist
from schemas.watchlist import (
    EntityEvaluationResult,
    WatchlistCreate,
    WatchlistDelivery,
    WatchlistEvaluationResponse,
    WatchlistResponse,
    WatchlistThresholds,
)
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from state_products.location_state.schema import LocationState, OperationalState

from services.location_state_service import LocationStateService

# Severity rank for the watchlist-level rollup. Highest wins.
_STATE_RANK = {
    OperationalState.NORMAL: 0,
    OperationalState.ELEVATED: 1,
    OperationalState.WATCH: 2,
    OperationalState.DISRUPTED: 3,
    OperationalState.CRITICAL: 4,
}


class WatchlistService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_watchlist(self, body: WatchlistCreate) -> WatchlistResponse:
        watchlist = Watchlist(
            name=body.name,
            evaluation_cadence=body.time_window,
            meta={"time_window": body.time_window},
        )
        self.db.add(watchlist)
        await self.db.flush()

        for place in body.places:
            self.db.add(
                WatchedEntity(
                    watchlist_id=watchlist.id,
                    entity_type="location",
                    entity_ref=place,
                    threshold_rules=body.thresholds.model_dump(),
                    delivery_preferences=body.delivery.model_dump(),
                )
            )
        await self.db.commit()
        # Re-read through the same path as GET so create/get round-trips
        # byte-identically regardless of insertion order.
        return await self.get_watchlist(watchlist.id)

    async def get_watchlist(self, watchlist_id: uuid.UUID) -> WatchlistResponse:
        watchlist, entities = await self._load_watchlist(watchlist_id)
        return _to_response(watchlist, entities)

    async def evaluate_watchlist(
        self,
        watchlist_id: uuid.UUID,
    ) -> WatchlistEvaluationResponse:
        watchlist, entities = await self._load_watchlist(watchlist_id)
        time_window = _time_window(watchlist)
        evaluated_at = datetime.now(timezone.utc)

        results: list[EntityEvaluationResult] = []
        for entity in entities:
            state = await LocationStateService(self.db).get_location_state(
                place=entity.entity_ref,
                time_window=time_window,
            )
            previous = await self._load_previous_result(entity.id)
            score_delta = (
                None if previous is None else round(state.risk_score - previous.current_score, 4)
            )
            material_change = _is_material_change(
                state=state,
                previous=previous,
                thresholds=WatchlistThresholds.model_validate(entity.threshold_rules),
                score_delta=score_delta,
            )

            evaluation = StateEvaluationResult(
                watched_entity_id=entity.id,
                evaluated_at=evaluated_at,
                previous_state=None if previous is None else previous.current_state,
                current_state=state.operational_state.value,
                previous_score=None if previous is None else previous.current_score,
                current_score=state.risk_score,
                score_delta=score_delta,
                material_change=material_change,
                drivers=[d.model_dump(mode="json") for d in state.drivers],
                confidence=state.confidence,
                provenance=[p.model_dump(mode="json") for p in state.provenance],
                recommended_actions=[a.model_dump(mode="json") for a in state.recommended_actions],
            )
            self.db.add(evaluation)
            # Flush to materialize the server-generated id; downstream brief
            # generation keys off this StateEvaluationResult id.
            await self.db.flush()
            entity.last_evaluated_at = evaluated_at
            if material_change:
                entity.last_notified_state = state.operational_state.value
                entity.last_notified_at = evaluated_at

            results.append(
                EntityEvaluationResult(
                    watched_entity_id=entity.id,
                    evaluation_result_id=evaluation.id,
                    place=entity.entity_ref,
                    previous_state=None if previous is None else previous.current_state,
                    current_state=state.operational_state.value,
                    previous_score=None if previous is None else previous.current_score,
                    current_score=state.risk_score,
                    score_delta=score_delta,
                    material_change=material_change,
                    location_state=state,
                )
            )

        await self.db.commit()

        # Rollup: the highest-severity entity drives both the watchlist-level
        # operational_state and the backward-compatible single-entity view.
        lead = max(
            results,
            key=lambda r: (
                _STATE_RANK[r.location_state.operational_state],
                r.current_score,
            ),
        )
        return WatchlistEvaluationResponse(
            id=lead.evaluation_result_id,
            watchlist_id=watchlist.id,
            operational_state=lead.location_state.operational_state,
            evaluated_at=evaluated_at,
            entities=results,
            previous_state=lead.previous_state,
            current_state=lead.current_state,
            previous_score=lead.previous_score,
            current_score=lead.current_score,
            score_delta=lead.score_delta,
            material_change=any(r.material_change for r in results),
            location_state=lead.location_state,
        )

    async def _load_watchlist(
        self,
        watchlist_id: uuid.UUID,
    ) -> tuple[Watchlist, list[WatchedEntity]]:
        watchlist = (
            await self.db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
        ).scalar_one_or_none()
        if watchlist is None:
            raise HTTPException(status_code=404, detail="Watchlist not found")

        entities = list(
            (
                await self.db.execute(
                    select(WatchedEntity)
                    .where(WatchedEntity.watchlist_id == watchlist_id)
                    .where(WatchedEntity.entity_type == "location")
                    # created_at is transaction-stable (identical for rows
                    # inserted together), so order by entity_ref for a stable,
                    # round-trip-safe ordering.
                    .order_by(asc(WatchedEntity.entity_ref), asc(WatchedEntity.id))
                )
            )
            .scalars()
            .all()
        )
        if not entities:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        return watchlist, entities

    async def _load_previous_result(
        self,
        watched_entity_id: uuid.UUID,
    ) -> StateEvaluationResult | None:
        stmt = (
            select(StateEvaluationResult)
            .where(StateEvaluationResult.watched_entity_id == watched_entity_id)
            .order_by(desc(StateEvaluationResult.evaluated_at))
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


def _to_response(
    watchlist: Watchlist,
    entities: list[WatchedEntity],
) -> WatchlistResponse:
    lead = entities[0]
    return WatchlistResponse(
        id=watchlist.id,
        name=watchlist.name,
        place=lead.entity_ref,
        places=[e.entity_ref for e in entities],
        time_window=_time_window(watchlist),
        thresholds=WatchlistThresholds.model_validate(lead.threshold_rules),
        delivery=WatchlistDelivery.model_validate(lead.delivery_preferences),
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


def _time_window(watchlist: Watchlist) -> str:
    return str(watchlist.meta.get("time_window") or watchlist.evaluation_cadence)


def _is_material_change(
    *,
    state: LocationState,
    previous: StateEvaluationResult | None,
    thresholds: WatchlistThresholds,
    score_delta: float | None,
) -> bool:
    if state.operational_state.value in thresholds.notify_on_state:
        return True
    if previous is None:
        return False
    if previous.current_state != state.operational_state.value:
        return True
    return score_delta is not None and abs(score_delta) >= thresholds.min_score_delta
