"""Live-data resilience: one bad dataset/row can't sink a run. No DB."""

from __future__ import annotations

import pytest
from ingestion.nyc import NycOpenDataCollector


class _RaisingClient:
    async def query_since(self, *a, **k):
        raise RuntimeError("Socrata 404 / renamed dataset")

    async def query(self, *a, **k):
        raise RuntimeError("network down")


class _PartialClient:
    """Returns one good 311 row and one missing the required key."""

    async def query_since(self, *a, **k):
        return [
            {"unique_key": "OK1", "complaint_type": "Noise", "borough": "BROOKLYN"},
            {"complaint_type": "Noise"},  # missing unique_key -> normalizer raises
        ]

    async def query(self, *a, **k):
        return await self.query_since()


@pytest.mark.asyncio
async def test_unreachable_dataset_yields_empty_not_exception():
    collector = NycOpenDataCollector(_RaisingClient())
    from datetime import datetime, timezone

    out = await collector.collect("311", since=datetime.now(timezone.utc))
    assert out == []
    out2 = await collector.collect("311")
    assert out2 == []


@pytest.mark.asyncio
async def test_one_bad_record_does_not_drop_the_dataset():
    collector = NycOpenDataCollector(_PartialClient())
    from datetime import datetime, timezone

    out = await collector.collect("311", since=datetime.now(timezone.utc))
    assert len(out) == 1
    assert out[0].external_id == "OK1"
