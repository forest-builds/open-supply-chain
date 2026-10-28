from __future__ import annotations

from datetime import datetime, timezone

import pytest
from ingestion.nyc import normalize_311_complaint
from models.raw_record import RawRecord
from models.signal import Signal
from models.source import Source
from services.nyc_signal_ingestion_service import NycSignalIngestionService
from sqlalchemy import select


def _normalized_signal(unique_key: str = "311-1"):
    return normalize_311_complaint(
        {
            "unique_key": unique_key,
            "created_date": "2026-05-11T12:00:00",
            "complaint_type": "HEAT/HOT WATER",
            "descriptor": "No Heat",
            "borough": "BROOKLYN",
            "incident_zip": "11201",
        }
    )


@pytest.mark.asyncio
async def test_ingest_nyc_signal_creates_source_raw_record_and_signal(db_session):
    result = await NycSignalIngestionService(db_session).ingest_signals(
        [_normalized_signal()],
    )

    assert result.seen == 1
    assert result.inserted == 1
    assert result.skipped == 0

    source = await db_session.scalar(select(Source).where(Source.name == "nyc-311"))
    assert source is not None
    assert source.source_type == "nyc_open_data"

    raw_record = await db_session.scalar(
        select(RawRecord).where(RawRecord.external_id == "311-1"),
    )
    assert raw_record is not None
    assert raw_record.source_id == source.id
    assert raw_record.record_type == "nyc_311_complaint"
    assert raw_record.source_updated_at == datetime(2026, 5, 11, 12, tzinfo=timezone.utc)

    signal = await db_session.scalar(select(Signal).where(Signal.raw_record_id == raw_record.id))
    assert signal is not None
    assert signal.signal_type == "civic_complaint"
    assert signal.severity == "High"
    assert signal.location["borough"] == "BROOKLYN"


@pytest.mark.asyncio
async def test_ingest_nyc_signal_is_idempotent_by_source_and_external_id(db_session):
    service = NycSignalIngestionService(db_session)

    first = await service.ingest_signals([_normalized_signal()])
    second = await service.ingest_signals([_normalized_signal()])

    raw_count = len((await db_session.execute(select(RawRecord))).scalars().all())
    signal_count = len((await db_session.execute(select(Signal))).scalars().all())
    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped == 1
    assert raw_count == 1
    assert signal_count == 1
