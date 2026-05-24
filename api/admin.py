from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

admin_router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def _ingest_noaa_alerts() -> None:
    try:
        from pipelines.noaa import run_alerts  # noqa: PLC0415

        run_alerts(dry_run=False)
    except Exception:
        logger.exception("NOAA alerts ingestion failed")


def _ingest_noaa_stations() -> None:
    try:
        from pipelines.noaa import run  # noqa: PLC0415

        run(dry_run=False)
    except Exception:
        logger.exception("NOAA stations ingestion failed")


def _ingest_usgs_quakes(days: int, min_magnitude: float) -> None:
    try:
        from pipelines.usgs_quakes import run  # noqa: PLC0415

        run(dry_run=False, days=days, min_magnitude=min_magnitude)
    except Exception:
        logger.exception("USGS earthquake ingestion failed")


def _ingest_usgs_water() -> None:
    try:
        from pipelines.usgs_water import run  # noqa: PLC0415

        run(dry_run=False)
    except Exception:
        logger.exception("USGS water gauge ingestion failed")


def _rebuild_impact_network() -> None:
    try:
        from pipelines.db import db_connection  # noqa: PLC0415
        from pipelines.impact_network import (  # noqa: PLC0415
            SOURCE_API_URL,
            SOURCE_NAME,
            ensure_source,
            rebuild_risk_impacts,
        )

        with db_connection() as conn:
            source_id = ensure_source(
                conn, SOURCE_NAME, SOURCE_API_URL, False, "after risk/entity ingestion", {}
            )
            count = rebuild_risk_impacts(conn, source_id)
            conn.commit()
        logger.info("Rebuilt %d risk impact edges", count)
    except Exception:
        logger.exception("Impact network rebuild failed")


@admin_router.post("/ingest/noaa-alerts")
def ingest_noaa_alerts(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Trigger a live refresh of NOAA NWS active weather alerts for the tri-state AOI."""
    background_tasks.add_task(_ingest_noaa_alerts)
    return {
        "status": "accepted",
        "pipeline": "noaa-alerts",
        "message": "NOAA NWS active alerts ingestion started in background.",
    }


@admin_router.post("/ingest/noaa-stations")
def ingest_noaa_stations(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Trigger a refresh of NOAA CDO weather station records. Requires NOAA_CDO_TOKEN."""
    if not os.environ.get("NOAA_CDO_TOKEN"):
        raise HTTPException(
            status_code=400, detail="NOAA_CDO_TOKEN environment variable is not set."
        )
    background_tasks.add_task(_ingest_noaa_stations)
    return {
        "status": "accepted",
        "pipeline": "noaa-stations",
        "message": "NOAA CDO weather stations ingestion started in background.",
    }


@admin_router.post("/ingest/usgs-quakes")
def ingest_usgs_quakes(
    background_tasks: BackgroundTasks,
    days: int = 30,
    min_magnitude: float = 1.0,
) -> dict[str, Any]:
    """Fetch USGS earthquake events for the tri-state AOI and load as risk_events."""
    background_tasks.add_task(_ingest_usgs_quakes, days, min_magnitude)
    return {
        "status": "accepted",
        "pipeline": "usgs-quakes",
        "message": f"USGS earthquake ingestion started (M{min_magnitude}+, last {days}d).",
    }


@admin_router.post("/ingest/usgs-water")
def ingest_usgs_water(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Fetch USGS active stream gauge sites for NY/NJ/CT and load as location entities."""
    background_tasks.add_task(_ingest_usgs_water)
    return {
        "status": "accepted",
        "pipeline": "usgs-water",
        "message": "USGS water gauge ingestion started.",
    }


@admin_router.post("/ingest/impact-network")
def ingest_impact_network(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Rebuild the risk_impacts edge table from current risk_events and geo_entities."""
    background_tasks.add_task(_rebuild_impact_network)
    return {
        "status": "accepted",
        "pipeline": "impact-network",
        "message": "Risk impact network rebuild started in background.",
    }
