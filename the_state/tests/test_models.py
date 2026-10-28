"""Smoke tests: model imports, table name sanity, metadata registration."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


def test_all_models_importable():
    from models import (
        Brief,
        Entity,
        FeedbackLog,
        Incident,
        IngestionRun,
        RawRecord,
        Signal,
        Source,
        StateEvaluationResult,
        StateSnapshot,
        TimelineEvent,
        WatchedEntity,
        Watchlist,
    )

    assert Brief.__tablename__ == "briefs"
    assert Entity.__tablename__ == "entities"
    assert FeedbackLog.__tablename__ == "feedback_logs"
    assert Incident.__tablename__ == "incidents"
    assert IngestionRun.__tablename__ == "ingestion_runs"
    assert RawRecord.__tablename__ == "raw_records"
    assert Signal.__tablename__ == "signals"
    assert Source.__tablename__ == "sources"
    assert StateEvaluationResult.__tablename__ == "state_evaluation_results"
    assert StateSnapshot.__tablename__ == "state_snapshots"
    assert TimelineEvent.__tablename__ == "timeline_events"
    assert WatchedEntity.__tablename__ == "watched_entities"
    assert Watchlist.__tablename__ == "watchlists"


def test_models_registered_in_metadata():
    import models  # noqa: F401
    from core.db import Base

    table_names = set(Base.metadata.tables.keys())
    expected = {
        "entities",
        "feedback_logs",
        "incidents",
        "ingestion_runs",
        "raw_records",
        "signals",
        "sources",
        "state_evaluation_results",
        "state_snapshots",
        "timeline_events",
        "watched_entities",
        "watchlists",
    }
    assert expected.issubset(table_names)


def test_source_column_names():
    from models.source import Source

    cols = {c.name for c in Source.__table__.columns}
    assert "id" in cols
    assert "name" in cols
    assert "source_type" in cols
    assert "metadata" in cols  # DB column is 'metadata', Python attr is 'meta'
    assert "created_at" in cols
    assert "updated_at" in cols


def test_raw_record_has_payload_hash_column():
    from models.raw_record import RawRecord

    cols = {c.name for c in RawRecord.__table__.columns}
    assert "payload_hash" in cols
    assert "payload" in cols
    assert "external_id" in cols
