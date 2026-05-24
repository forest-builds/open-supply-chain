from datetime import datetime, timezone

from api.routes import (
    fallback_geo_features,
    geo_summary,
    geo_sources,
    list_geo_entities,
    list_risk_event_impacts,
    list_risk_events,
    risk_scores,
    risk_impacts_summary,
    risk_summary,
)


def test_fallback_geo_features_reads_seed_payload() -> None:
    features = fallback_geo_features("port", limit=2)

    assert len(features) == 2
    assert features[0]["type"] == "Feature"
    assert features[0]["properties"]["entity_type"] == "port"
    assert features[0]["properties"]["storage"] == "local_raw_fallback"


def test_list_geo_entities_uses_fallback_when_db_unavailable(monkeypatch) -> None:
    class BrokenConnection:
        def __enter__(self):
            import psycopg

            raise psycopg.OperationalError("db unavailable")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("api.routes.get_connection", lambda: BrokenConnection())
    response = list_geo_entities(entity_type="port", limit=1)

    assert response["type"] == "FeatureCollection"
    assert len(response["features"]) == 1
    assert response["features"][0]["properties"]["storage"] == "local_raw_fallback"


def test_geo_summary_uses_fallback_when_db_unavailable(monkeypatch) -> None:
    class BrokenConnection:
        def __enter__(self):
            import psycopg

            raise psycopg.OperationalError("db unavailable")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("api.routes.get_connection", lambda: BrokenConnection())
    response = geo_summary()

    assert {"entity_type": "port", "count": 224} in response


def test_list_risk_events_returns_geojson(monkeypatch) -> None:
    class FakeCursor:
        def fetchall(self):
            return [
                {
                    "id": "risk-1",
                    "event_type": "Coastal Flood Advisory",
                    "severity": "Minor",
                    "certainty": "Likely",
                    "urgency": "Expected",
                    "headline": "Coastal flooding could affect port approaches",
                    "description": "Water levels may disrupt low-lying infrastructure.",
                    "instruction": "Use caution.",
                    "area_desc": "Hudson County",
                    "effective_at": datetime(2026, 5, 24, 12, tzinfo=timezone.utc),
                    "expires_at": None,
                    "source_name": "NOAA NWS",
                    "source_event_id": "nws-alert-1",
                    "source_tags": {"phenomenon": "CF"},
                    "confidence": 0.9,
                    "geometry": {"type": "Polygon", "coordinates": []},
                }
            ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args):
            return FakeCursor()

    monkeypatch.setattr("api.routes.get_connection", lambda: FakeConnection())
    response = list_risk_events(limit=10)

    assert response["type"] == "FeatureCollection"
    assert response["features"][0]["properties"]["record_type"] == "risk_event"
    assert response["features"][0]["properties"]["event_type"] == "Coastal Flood Advisory"
    assert response["features"][0]["properties"]["effective_at"] == "2026-05-24T12:00:00+00:00"
    assert response["features"][0]["geometry"]["type"] == "Polygon"


def test_risk_summary_groups_events(monkeypatch) -> None:
    class FakeCursor:
        def fetchall(self):
            return [{"severity": "Moderate", "event_type": "Rip Current Statement", "count": 3}]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args):
            return FakeCursor()

    monkeypatch.setattr("api.routes.get_connection", lambda: FakeConnection())

    assert risk_summary() == [
        {"severity": "Moderate", "event_type": "Rip Current Statement", "count": 3}
    ]


def test_list_risk_event_impacts_returns_geojson(monkeypatch) -> None:
    class FakeCursor:
        def fetchall(self):
            return [
                {
                    "id": "asset-1",
                    "entity_type": "port",
                    "subtype": "marina",
                    "name": "Test Port",
                    "description": None,
                    "source_name": "openstreetmap",
                    "source_entity_id": "way/1",
                    "source_tags": {"name": "Test Port"},
                    "confidence": 0.8,
                    "impact_method": "intersects",
                    "distance_m": 0.0,
                    "impact_confidence": 0.85,
                    "evidence": {"rule": "test"},
                    "geometry": {"type": "Point", "coordinates": [-74, 40.7]},
                }
            ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args):
            return FakeCursor()

    monkeypatch.setattr("api.routes.get_connection", lambda: FakeConnection())
    response = list_risk_event_impacts(event_id="risk-1", limit=10)

    assert response["type"] == "FeatureCollection"
    assert response["features"][0]["properties"]["impact_method"] == "intersects"
    assert response["features"][0]["properties"]["impact_evidence"] == {"rule": "test"}


def test_risk_impacts_summary_groups_impacts(monkeypatch) -> None:
    class FakeCursor:
        def fetchall(self):
            return [{"entity_type": "port", "impact_method": "intersects", "count": 12}]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args):
            return FakeCursor()

    monkeypatch.setattr("api.routes.get_connection", lambda: FakeConnection())

    assert risk_impacts_summary() == [
        {"entity_type": "port", "impact_method": "intersects", "count": 12}
    ]


def test_risk_scores_returns_weighted_geojson(monkeypatch) -> None:
    class FakeCursor:
        def fetchall(self):
            return [
                {
                    "id": "asset-1",
                    "entity_type": "port",
                    "subtype": None,
                    "name": "Test Port",
                    "source_name": "openstreetmap",
                    "geometry": {"type": "Point", "coordinates": [-74, 40.7]},
                    "impact_count": 2,
                    "risk_score": 2.55,
                    "top_severity": "Moderate",
                }
            ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args):
            return FakeCursor()

    monkeypatch.setattr("api.routes.get_connection", lambda: FakeConnection())
    response = risk_scores(entity_type="port", limit=10)

    assert response["features"][0]["properties"]["record_type"] == "risk_score"
    assert response["features"][0]["properties"]["risk_score"] == 2.55


def test_risk_scores_returns_empty_when_db_unavailable(monkeypatch) -> None:
    class BrokenConnection:
        def __enter__(self):
            import psycopg

            raise psycopg.OperationalError("db unavailable")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("api.routes.get_connection", lambda: BrokenConnection())

    assert risk_scores()["features"] == []


def test_geo_sources_returns_sources_and_fallback_empty(monkeypatch) -> None:
    class FakeCursor:
        def fetchall(self):
            return [
                {
                    "name": "openstreetmap",
                    "api_url": "https://overpass.test",
                    "attribution": "OSM contributors",
                    "license": "ODbL",
                    "refresh_rate": "weekly",
                    "entity_count": 10,
                    "last_ingested_at": datetime(2026, 5, 24, tzinfo=timezone.utc),
                }
            ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *_args):
            return FakeCursor()

    monkeypatch.setattr("api.routes.get_connection", lambda: FakeConnection())
    assert geo_sources()[0]["name"] == "openstreetmap"

    class BrokenConnection:
        def __enter__(self):
            import psycopg

            raise psycopg.OperationalError("db unavailable")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("api.routes.get_connection", lambda: BrokenConnection())
    assert geo_sources() == []
