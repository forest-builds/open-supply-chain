"""NormalizerProtocol conformance (Task 1.3). No DB required."""

from __future__ import annotations

from datetime import datetime, timezone

from ingestion import NormalizedSignal, NormalizerProtocol
from ingestion.nyc import NycNormalizer, nyc_normalizer


def test_nyc_normalizer_satisfies_protocol():
    assert isinstance(nyc_normalizer, NormalizerProtocol)
    assert isinstance(NycNormalizer(), NormalizerProtocol)


def test_normalized_signal_is_shared_from_base():
    # nyc must reuse the canonical base type, not a divergent copy.
    from ingestion.base import NormalizedSignal as BaseSignal
    from ingestion.nyc import NormalizedSignal as NycSignal

    assert NycSignal is BaseSignal is NormalizedSignal


def test_nyc_normalizer_delegates_to_registry():
    record = {
        "unique_key": "C1",
        "complaint_type": "Noise",
        "created_date": "2026-05-10T12:00:00.000",
        "borough": "BROOKLYN",
    }
    via_class = nyc_normalizer.normalize_record("311", record)
    assert isinstance(via_class, NormalizedSignal)
    assert via_class.external_id == "C1"
    assert via_class.signal_type == "civic_complaint"
    # observed_at must be tz-aware UTC.
    assert via_class.observed_at.tzinfo is not None
    assert via_class.observed_at <= datetime.now(timezone.utc)
