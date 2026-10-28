from __future__ import annotations

from datetime import datetime, timezone

import pytest
from ingestion.nyc import NycDatasetName, normalize_311_complaint
from models.watchlist import Watchlist
from services.nyc_living_artifact_service import NycLivingArtifactService
from sqlalchemy import select


class FakeCollector:
    def __init__(self) -> None:
        self.calls: list[tuple[NycDatasetName, datetime | None, int]] = []

    async def collect(
        self,
        dataset_name: NycDatasetName,
        *,
        since: datetime | None = None,
        limit: int = 1000,
        where: str | None = None,
    ):
        self.calls.append((dataset_name, since, limit))
        return [
            normalize_311_complaint(
                {
                    "unique_key": "311-heat-1",
                    "created_date": datetime.now(timezone.utc).isoformat(),
                    "complaint_type": "HEAT/HOT WATER",
                    "descriptor": "No Heat",
                    "borough": "BROOKLYN",
                    "incident_zip": "11201",
                }
            )
        ]


@pytest.mark.asyncio
async def test_nyc_living_artifact_fetches_persists_evaluates_and_briefs(db_session):
    collector = FakeCollector()
    since = datetime(2026, 5, 11, 0, 0, tzinfo=timezone.utc)

    result = await NycLivingArtifactService(db_session, collector).run(
        place="Brooklyn, NYC",
        watchlist_name="Brooklyn Living Watch",
        since=since,
        dataset_names=["311"],
        limit_per_dataset=5,
        brief_base_url="https://state.example",
    )

    assert collector.calls == [("311", since, 5)]
    assert result.place == "Brooklyn, NYC"
    assert result.time_window == "24h"
    assert result.since == since
    assert result.datasets[0].dataset == "311"
    assert result.datasets[0].collected == 1
    assert result.signals_seen == 1
    assert result.signals_inserted == 1
    assert result.signals_skipped == 0
    assert result.operational_state == "normal"
    assert result.risk_score == pytest.approx(0.10)
    assert result.active_signal_count == 1
    assert result.summary.startswith("Brooklyn, NYC is normal")
    assert result.drivers[0]["label"] == "311 civic complaints"
    assert result.recommended_actions[0]["action"] == "Continue normal operations"
    assert result.evidence[0]["source"] == "nyc-311"
    assert result.provenance[0]["source"] == "nyc-311"
    assert result.brief_url == f"https://state.example/briefs/{result.brief_id}"


@pytest.mark.asyncio
async def test_nyc_living_artifact_reuses_watchlist_and_skips_existing_raw_records(db_session):
    collector = FakeCollector()
    service = NycLivingArtifactService(db_session, collector)

    first = await service.run(
        place="Brooklyn, NYC",
        watchlist_name="Brooklyn Living Watch",
        dataset_names=["311"],
    )
    second = await service.run(
        place="Brooklyn, NYC",
        watchlist_name="Brooklyn Living Watch",
        dataset_names=["311"],
    )

    watchlists = (await db_session.execute(select(Watchlist))).scalars().all()
    assert len(watchlists) == 1
    assert second.watchlist_id == first.watchlist_id
    assert second.signals_inserted == 0
    assert second.signals_skipped == 1
    assert second.evaluation_result_id != first.evaluation_result_id
    assert second.brief_id != first.brief_id
