from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from ingestion.nyc import NYC_DATASETS, NormalizedSignal, NycDatasetName, NycOpenDataCollector
from models.watched_entity import WatchedEntity
from models.watchlist import Watchlist
from pydantic import BaseModel
from schemas.brief import BriefGenerateRequest, BriefResponse
from schemas.watchlist import WatchlistCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from state_products.location_state.decision import decide
from state_products.location_state.schema import LocationState

from services.brief_service import BriefService
from services.decision_service import (
    _COVERAGE_WARNING,
    EXCLUDED_SOURCES,
    INCLUDED_SOURCES,
)
from services.location_state_service import LocationStateService
from services.nyc_signal_ingestion_service import (
    NycSignalIngestionResult,
    NycSignalIngestionService,
)
from services.watchlist_service import WatchlistService


class NycCollector(Protocol):
    async def collect(
        self,
        dataset_name: NycDatasetName,
        *,
        since: datetime | None = None,
        limit: int = 1000,
        where: str | None = None,
    ) -> list[NormalizedSignal]: ...


class NycDatasetRun(BaseModel):
    dataset: NycDatasetName
    collected: int


class NycLivingArtifactResult(BaseModel):
    place: str
    time_window: str
    generated_at: datetime
    since: datetime
    datasets: list[NycDatasetRun]
    signals_seen: int
    signals_inserted: int
    signals_skipped: int
    watchlist_id: uuid.UUID
    evaluation_result_id: uuid.UUID
    brief_id: uuid.UUID
    brief_url: str
    operational_state: str
    risk_score: float
    active_signal_count: int
    summary: str
    what_changed: str
    why_it_matters: str
    drivers: list[dict[str, Any]]
    active_signals: list[dict[str, Any]]
    recent_changes: list[dict[str, Any]]
    recommended_actions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    confidence: float
    provenance: list[dict[str, Any]]
    sub_locations: list[dict[str, Any]] = []
    content_hash: str = ""
    history: list[dict[str, Any]] = []
    decision: dict[str, Any] = {}
    coverage: dict[str, Any] = {}


class NycLivingArtifactService:
    def __init__(
        self,
        db: AsyncSession,
        collector: NycCollector,
    ) -> None:
        self.db = db
        self.collector = collector

    async def run(
        self,
        *,
        place: str = "New York, NY",
        watchlist_name: str = "NYC Living Watchlist",
        time_window: str = "24h",
        since: datetime | None = None,
        dataset_names: list[NycDatasetName] | None = None,
        limit_per_dataset: int = 100,
        brief_base_url: str = "http://localhost:8000",
    ) -> NycLivingArtifactResult:
        since = since or datetime.now(timezone.utc) - timedelta(hours=24)
        dataset_names = dataset_names or list(NYC_DATASETS)

        dataset_runs: list[NycDatasetRun] = []
        normalized_signals = []
        for dataset_name in dataset_names:
            signals = await self.collector.collect(
                dataset_name,
                since=since,
                limit=limit_per_dataset,
            )
            normalized_signals.extend(signals)
            dataset_runs.append(NycDatasetRun(dataset=dataset_name, collected=len(signals)))

        ingestion = await NycSignalIngestionService(self.db).ingest_signals(
            normalized_signals,
        )
        watchlist_id = await self._get_or_create_watchlist(
            name=watchlist_name,
            place=place,
            time_window=time_window,
        )
        evaluation = await WatchlistService(self.db).evaluate_watchlist(watchlist_id)

        brief_service = BriefService(self.db)
        brief = await brief_service.generate(
            body=BriefGenerateRequest(evaluation_result_id=evaluation.id),
        )
        brief_response = await brief_service.to_response(
            brief,
            url=_brief_url(brief_base_url, brief.id),
        )

        history = await LocationStateService(self.db).get_location_state_history(
            place=place,
            from_dt=datetime.now(timezone.utc) - timedelta(days=7),
            to_dt=datetime.now(timezone.utc),
            limit=12,
        )

        return _to_result(
            place=place,
            time_window=time_window,
            since=since,
            dataset_runs=dataset_runs,
            ingestion=ingestion,
            watchlist_id=watchlist_id,
            evaluation_id=evaluation.id,
            brief=brief_response,
            location_state=evaluation.location_state,
            history=[h.model_dump(mode="json") for h in history],
        )

    async def _get_or_create_watchlist(
        self,
        *,
        name: str,
        place: str,
        time_window: str,
    ) -> uuid.UUID:
        stmt = (
            select(Watchlist.id)
            .join(WatchedEntity, WatchedEntity.watchlist_id == Watchlist.id)
            .where(Watchlist.name == name)
            .where(WatchedEntity.entity_type == "location")
            .where(WatchedEntity.entity_ref == place)
            .limit(1)
        )
        existing_id = await self.db.scalar(stmt)
        if existing_id is not None:
            return existing_id

        created = await WatchlistService(self.db).create_watchlist(
            WatchlistCreate(
                name=name,
                place=place,
                time_window=time_window,
            )
        )
        return created.id


def build_nyc_living_artifact_service(
    db: AsyncSession,
    collector: NycOpenDataCollector,
) -> NycLivingArtifactService:
    return NycLivingArtifactService(db, collector)


def _to_result(
    *,
    place: str,
    time_window: str,
    since: datetime,
    dataset_runs: list[NycDatasetRun],
    ingestion: NycSignalIngestionResult,
    watchlist_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    brief: BriefResponse,
    location_state: LocationState,
    history: list[dict[str, Any]] | None = None,
) -> NycLivingArtifactResult:
    return NycLivingArtifactResult(
        place=place,
        time_window=time_window,
        generated_at=brief.generated_at,
        since=since,
        datasets=dataset_runs,
        signals_seen=ingestion.seen,
        signals_inserted=ingestion.inserted,
        signals_skipped=ingestion.skipped,
        watchlist_id=watchlist_id,
        evaluation_result_id=evaluation_id,
        brief_id=brief.id,
        brief_url=brief.url,
        operational_state=brief.operational_state,
        risk_score=brief.risk_score,
        active_signal_count=len(location_state.active_signals),
        summary=brief.summary,
        what_changed=brief.what_changed,
        why_it_matters=brief.why_it_matters,
        drivers=[driver.model_dump(mode="json") for driver in location_state.drivers],
        active_signals=[signal.model_dump(mode="json") for signal in location_state.active_signals],
        recent_changes=[change.model_dump(mode="json") for change in location_state.recent_changes],
        recommended_actions=[
            action.model_dump(mode="json") for action in location_state.recommended_actions
        ],
        evidence=brief.evidence,
        confidence=brief.confidence,
        provenance=[item.model_dump(mode="json") for item in location_state.provenance],
        sub_locations=[sub.model_dump(mode="json") for sub in location_state.sub_locations],
        content_hash=brief.content_hash,
        history=history or [],
        decision=asdict(
            decide(
                operational_state=location_state.operational_state,
                risk_score=location_state.risk_score,
                confidence=location_state.confidence,
                time_window="next_4_hours",
                operation_type="field_dispatch",
                risk_tolerance="normal",
            )
        ),
        coverage={
            "level": "limited",
            "included": INCLUDED_SOURCES,
            "excluded": EXCLUDED_SOURCES,
            "warning": _COVERAGE_WARNING,
        },
    )


def _brief_url(base_url: str, brief_id: uuid.UUID) -> str:
    return f"{base_url.rstrip('/')}/briefs/{brief_id}"
