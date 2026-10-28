from __future__ import annotations

from dataclasses import dataclass

from core.hashing import hash_payload
from ingestion.nyc import NormalizedSignal
from models.raw_record import RawRecord
from models.signal import Signal
from models.source import Source
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class NycSignalIngestionResult:
    seen: int
    inserted: int
    skipped: int


class NycSignalIngestionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ingest_signals(
        self,
        signals: list[NormalizedSignal],
    ) -> NycSignalIngestionResult:
        inserted = 0
        skipped = 0
        source_cache: dict[str, Source] = {}

        for signal in signals:
            source = source_cache.get(signal.source_name)
            if source is None:
                source = await self._get_or_create_source(signal)
                source_cache[signal.source_name] = source

            exists = await self._raw_record_exists(
                source_id=source.id,
                external_id=signal.external_id,
            )
            if exists:
                skipped += 1
                continue

            raw_record = RawRecord(
                source_id=source.id,
                external_id=signal.external_id,
                record_type=signal.record_type,
                payload=signal.payload,
                payload_hash=hash_payload(signal.payload),
                observed_at=signal.observed_at,
                source_updated_at=signal.occurred_at,
            )
            self.db.add(raw_record)
            await self.db.flush()

            self.db.add(
                Signal(
                    source_id=source.id,
                    raw_record_id=raw_record.id,
                    signal_type=signal.signal_type,
                    title=signal.title,
                    summary=signal.summary,
                    severity=signal.severity,
                    confidence=1.0,
                    occurred_at=signal.occurred_at,
                    observed_at=signal.observed_at,
                    location=signal.location,
                    attributes=signal.attributes,
                )
            )
            inserted += 1

        await self.db.commit()
        return NycSignalIngestionResult(
            seen=len(signals),
            inserted=inserted,
            skipped=skipped,
        )

    async def _get_or_create_source(self, signal: NormalizedSignal) -> Source:
        source = await self.db.scalar(
            select(Source).where(Source.name == signal.source_name),
        )
        if source is not None:
            return source

        source = Source(
            name=signal.source_name,
            source_type=signal.source_type,
            base_url="https://data.cityofnewyork.us/resource",
            description=f"NYC Open Data source for {signal.record_type}",
            meta={"record_type": signal.record_type},
        )
        self.db.add(source)
        await self.db.flush()
        return source

    async def _raw_record_exists(
        self,
        *,
        source_id,
        external_id: str,
    ) -> bool:
        stmt = (
            select(RawRecord.id)
            .where(RawRecord.source_id == source_id)
            .where(RawRecord.external_id == external_id)
            .limit(1)
        )
        return await self.db.scalar(stmt) is not None
