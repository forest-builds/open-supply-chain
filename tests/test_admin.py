import pytest
from fastapi import BackgroundTasks, HTTPException

import api.admin as admin


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args):
        self.tasks.append((func, args))


def test_ingest_noaa_alerts_schedules_background_task() -> None:
    tasks = FakeBackgroundTasks()

    response = admin.ingest_noaa_alerts(tasks)  # type: ignore[arg-type]

    assert response["status"] == "accepted"
    assert response["pipeline"] == "noaa-alerts"
    assert tasks.tasks == [(admin._ingest_noaa_alerts, ())]


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
    assert tasks.tasks == [(admin._ingest_noaa_stations, ())]


def test_ingest_impact_network_schedules_background_task() -> None:
    tasks = FakeBackgroundTasks()

    response = admin.ingest_impact_network(tasks)  # type: ignore[arg-type]

    assert response["status"] == "accepted"
    assert response["pipeline"] == "impact-network"
    assert tasks.tasks == [(admin._rebuild_impact_network, ())]


def test_new_admin_ingest_endpoints_schedule_tasks(monkeypatch) -> None:
    monkeypatch.setenv("EIA_API_KEY", "token")
    monkeypatch.setenv("AIS_API_KEY", "token")

    expected = [
        (admin.ingest_usgs_quakes, "usgs-quakes", admin._ingest_usgs_quakes, (30, 1.0)),
        (admin.ingest_usgs_water, "usgs-water", admin._ingest_usgs_water, ()),
        (admin.ingest_chain_network, "chain-network", admin._rebuild_chain_network, ()),
        (admin.ingest_gdacs, "gdacs", admin._ingest_gdacs, ()),
        (admin.ingest_epa, "epa", admin._ingest_epa, ()),
        (admin.ingest_eia, "eia", admin._ingest_eia, ()),
        (admin.ingest_usaspending, "usaspending", admin._ingest_usaspending, ()),
        (admin.ingest_ais, "ais", admin._ingest_ais, ()),
    ]
    for endpoint, pipeline, task, args in expected:
        tasks = FakeBackgroundTasks()

        response = endpoint(tasks)  # type: ignore[arg-type]

        assert response["status"] == "accepted"
        assert response["pipeline"] == pipeline
        assert tasks.tasks == [(task, args)]


def test_api_key_admin_endpoints_require_tokens(monkeypatch) -> None:
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    monkeypatch.delenv("AIS_API_KEY", raising=False)

    with pytest.raises(HTTPException) as eia_exc:
        admin.ingest_eia(BackgroundTasks())
    with pytest.raises(HTTPException) as ais_exc:
        admin.ingest_ais(BackgroundTasks())

    assert eia_exc.value.status_code == 400
    assert ais_exc.value.status_code == 400


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


def test_background_source_ingestions_call_pipeline_run(monkeypatch) -> None:
    called = []

    monkeypatch.setattr("pipelines.noaa.run_alerts", lambda dry_run: called.append(("alerts", dry_run)))
    monkeypatch.setattr("pipelines.noaa.run", lambda dry_run: called.append(("stations", dry_run)))
    monkeypatch.setattr(
        "pipelines.usgs_quakes.run",
        lambda dry_run, days, min_magnitude: called.append(
            ("quakes", dry_run, days, min_magnitude)
        ),
    )
    monkeypatch.setattr("pipelines.usgs_water.run", lambda dry_run: called.append(("water", dry_run)))
    monkeypatch.setattr("pipelines.gdacs.run", lambda dry_run: called.append(("gdacs", dry_run)))
    monkeypatch.setattr("pipelines.epa.run", lambda dry_run: called.append(("epa", dry_run)))
    monkeypatch.setattr("pipelines.eia.run", lambda dry_run: called.append(("eia", dry_run)))
    monkeypatch.setattr(
        "pipelines.usaspending.run",
        lambda dry_run: called.append(("usaspending", dry_run)),
    )
    monkeypatch.setattr("pipelines.ais.run", lambda dry_run: called.append(("ais", dry_run)))

    admin._ingest_noaa_alerts()
    admin._ingest_noaa_stations()
    admin._ingest_usgs_quakes(days=7, min_magnitude=2.5)
    admin._ingest_usgs_water()
    admin._ingest_gdacs()
    admin._ingest_epa()
    admin._ingest_eia()
    admin._ingest_usaspending()
    admin._ingest_ais()

    assert called == [
        ("alerts", False),
        ("stations", False),
        ("quakes", False, 7, 2.5),
        ("water", False),
        ("gdacs", False),
        ("epa", False),
        ("eia", False),
        ("usaspending", False),
        ("ais", False),
    ]


def test_background_new_ingestions_log_failure(monkeypatch, caplog) -> None:
    def broken_run(*_, **__):
        raise RuntimeError("boom")

    monkeypatch.setattr("pipelines.usgs_quakes.run", broken_run)
    monkeypatch.setattr("pipelines.usgs_water.run", broken_run)
    monkeypatch.setattr("pipelines.gdacs.run", broken_run)
    monkeypatch.setattr("pipelines.epa.run", broken_run)
    monkeypatch.setattr("pipelines.eia.run", broken_run)
    monkeypatch.setattr("pipelines.usaspending.run", broken_run)
    monkeypatch.setattr("pipelines.ais.run", broken_run)

    admin._ingest_usgs_quakes(days=7, min_magnitude=2.5)
    admin._ingest_usgs_water()
    admin._ingest_gdacs()
    admin._ingest_epa()
    admin._ingest_eia()
    admin._ingest_usaspending()
    admin._ingest_ais()

    assert "USGS earthquake ingestion failed" in caplog.text
    assert "USGS water gauge ingestion failed" in caplog.text
    assert "GDACS ingestion failed" in caplog.text
    assert "EPA TRI ingestion failed" in caplog.text
    assert "EIA ingestion failed" in caplog.text
    assert "USASpending ingestion failed" in caplog.text
    assert "AIS vessel ingestion failed" in caplog.text


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


def test_rebuild_chain_network_success(monkeypatch, caplog) -> None:
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
    monkeypatch.setattr("pipelines.chain_network.build_chain_network", lambda *args: 8)
    caplog.set_level("INFO", logger="api.admin")

    admin._rebuild_chain_network()

    assert conn.committed
    assert "Built 8 SERVED_BY_ROUTE edges" in caplog.text


def test_rebuild_chain_network_logs_failure(monkeypatch, caplog) -> None:
    def broken_connection():
        raise RuntimeError("db down")

    monkeypatch.setattr("pipelines.db.db_connection", broken_connection)

    admin._rebuild_chain_network()

    assert "Chain network build failed" in caplog.text
