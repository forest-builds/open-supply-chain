import pytest
from fastapi import BackgroundTasks, HTTPException

import api.admin as admin


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func):
        self.tasks.append(func)


def test_ingest_noaa_alerts_schedules_background_task() -> None:
    tasks = FakeBackgroundTasks()

    response = admin.ingest_noaa_alerts(tasks)  # type: ignore[arg-type]

    assert response["status"] == "accepted"
    assert response["pipeline"] == "noaa-alerts"
    assert tasks.tasks == [admin._ingest_noaa_alerts]


def test_ingest_noaa_stations_requires_token(monkeypatch) -> None:
    monkeypatch.delenv("NOAA_CDO_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        admin.ingest_noaa_stations(BackgroundTasks())

    assert exc.value.status_code == 400


def test_ingest_noaa_stations_schedules_background_task(monkeypatch) -> None:
    monkeypatch.setenv("NOAA_CDO_TOKEN", "token")
    tasks = FakeBackgroundTasks()

    response = admin.ingest_noaa_stations(tasks)  # type: ignore[arg-type]

    assert response["status"] == "accepted"
    assert response["pipeline"] == "noaa-stations"
    assert tasks.tasks == [admin._ingest_noaa_stations]


def test_ingest_impact_network_schedules_background_task() -> None:
    tasks = FakeBackgroundTasks()

    response = admin.ingest_impact_network(tasks)  # type: ignore[arg-type]

    assert response["status"] == "accepted"
    assert response["pipeline"] == "impact-network"
    assert tasks.tasks == [admin._rebuild_impact_network]


def test_background_noaa_alert_ingestion_logs_failure(monkeypatch, caplog) -> None:
    def broken_run_alerts(dry_run: bool) -> None:
        raise RuntimeError("boom")

    import pipelines.noaa

    monkeypatch.setattr(pipelines.noaa, "run_alerts", broken_run_alerts)

    admin._ingest_noaa_alerts()

    assert "NOAA alerts ingestion failed" in caplog.text


def test_background_noaa_station_ingestion_logs_failure(monkeypatch, caplog) -> None:
    def broken_run(dry_run: bool) -> None:
        raise RuntimeError("boom")

    import pipelines.noaa

    monkeypatch.setattr(pipelines.noaa, "run", broken_run)

    admin._ingest_noaa_stations()

    assert "NOAA stations ingestion failed" in caplog.text


def test_rebuild_impact_network_success(monkeypatch, caplog) -> None:
    class FakeConnection:
        committed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def commit(self):
            self.committed = True

    conn = FakeConnection()
    monkeypatch.setattr("pipelines.db.db_connection", lambda: conn)
    monkeypatch.setattr("pipelines.impact_network.ensure_source", lambda *args: "source-1")
    monkeypatch.setattr("pipelines.impact_network.rebuild_risk_impacts", lambda *args: 12)
    caplog.set_level("INFO", logger="api.admin")

    admin._rebuild_impact_network()

    assert conn.committed
    assert "Rebuilt 12 risk impact edges" in caplog.text


def test_rebuild_impact_network_logs_failure(monkeypatch, caplog) -> None:
    def broken_connection():
        raise RuntimeError("db down")

    monkeypatch.setattr("pipelines.db.db_connection", broken_connection)

    admin._rebuild_impact_network()

    assert "Impact network rebuild failed" in caplog.text
