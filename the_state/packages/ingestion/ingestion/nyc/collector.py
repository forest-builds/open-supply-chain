from __future__ import annotations

import logging
from datetime import datetime

from ingestion.nyc.datasets import NYC_DATASETS
from ingestion.nyc.normalizers import normalize_record
from ingestion.nyc.records import NormalizedSignal, NycDatasetName
from ingestion.nyc.socrata import SocrataClient

logger = logging.getLogger("ingestion.nyc")


class NycOpenDataCollector:
    def __init__(self, client: SocrataClient) -> None:
        self.client = client

    async def collect(
        self,
        dataset_name: NycDatasetName,
        *,
        since: datetime | None = None,
        limit: int = 1000,
        where: str | None = None,
    ) -> list[NormalizedSignal]:
        """Fetch + normalize one dataset.

        Hardened for live data: a dataset that is unreachable, renamed, or
        returns an unexpected schema must NOT sink the whole run. The fetch
        is isolated (returns [] on failure) and each record is normalized
        independently so one malformed row can't drop the dataset.
        """
        config = NYC_DATASETS[dataset_name]
        try:
            if since is not None:
                records = await self.client.query_since(
                    config.dataset_id,
                    date_field=config.date_field,
                    since=since,
                    limit=limit,
                    order=config.default_order,
                )
            else:
                records = await self.client.query(
                    config.dataset_id,
                    where=where,
                    limit=limit,
                    order=config.default_order,
                )
        except Exception as exc:  # noqa: BLE001 - external boundary, skip source
            logger.warning(
                "NYC collect skipped dataset=%s id=%s: %s",
                dataset_name,
                config.dataset_id,
                exc,
            )
            return []

        signals: list[NormalizedSignal] = []
        skipped = 0
        for record in records:
            try:
                signals.append(normalize_record(dataset_name, record))
            except Exception as exc:  # noqa: BLE001 - one bad row, not the set
                skipped += 1
                logger.debug("NYC normalize skipped dataset=%s: %s", dataset_name, exc)
        if skipped:
            logger.warning(
                "NYC normalize dropped %d/%d records for dataset=%s",
                skipped,
                len(records),
                dataset_name,
            )
        return signals
