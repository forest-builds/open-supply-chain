from uuid import uuid4

import psycopg
import pytest

from api.tools import (
    assets_impacted_by_event,
    buffer_entity,
    catalog,
    entities_in_bbox,
    example_refrigerated_food_port_newark,
    facilities_near,
    gis_metadata,
    layer_metadata,
    ports_near,
    risk_events_near_asset,
    routes_near,
    routes_impacted_by_alert,
    search_entities,
    stream_gauges_near,
    summarize_asset_exposure,
    topology_relations_for_entity,
    weather_stations_near,
)


class _BrokenDB:
    def __enter__(self):
        raise psycopg.OperationalError("db unavailable")

    def __exit__(self, *args):
        return False


@pytest.fixture()
def no_db(monkeypatch):
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_lists_all_tools():
    result = catalog()
    assert result["tool_count"] == 22
    names = {t["name"] for t in result["tools"]}
    assert names == {
        "ports_near",
        "facilities_near",
        "weather_stations_near",
        "stream_gauges_near",
        "routes_near",
        "entities_in_bbox",
        "search_entities",
        "assets_impacted_by_event",
        "risk_events_near_asset",
        "routes_impacted_by_alert",
        "summarize_asset_exposure",
        "trace_supply_chain",
        "find_chain_assets",
        "gis_metadata",
        "layer_metadata",
        "topology_relations_for_entity",
        "buffer_entity",
        "example_refrigerated_food_port_newark",
        "active_alerts_near",
        "risk_events_near",
        "vessels_near",
        "corridor_risk_exposure",
    }


# ---------------------------------------------------------------------------
# Response shape — no DB required
# ---------------------------------------------------------------------------


def test_ports_near_shape_without_db(no_db):
    result = ports_near(lat=40.7, lon=-74.0, radius_km=50)
    assert result["tool"] == "ports_near"
    assert result["type"] == "FeatureCollection"
    assert result["count"] == 0
    assert result["features"] == []
    assert isinstance(result["explanation"], str)
    assert "port" in result["explanation"]
    assert result["parameters"]["radius_km"] == 50


def test_facilities_near_shape_without_db(no_db):
    result = facilities_near(lat=40.7, lon=-74.0, radius_km=30, subtype="warehouse")
    assert result["tool"] == "facilities_near"
    assert result["count"] == 0
    assert result["parameters"]["subtype"] == "warehouse"
    assert "warehouse" in result["explanation"]


def test_example_refrigerated_food_port_newark_shape_without_db(monkeypatch):
    monkeypatch.setattr("api.chains.get_connection", lambda: _BrokenDB())

    result = example_refrigerated_food_port_newark()

    assert result["tool"] == "example_refrigerated_food_port_newark"
    assert result["slug"] == "refrigerated-food-imports-port-newark"
    assert result["anchor_port"] is None
    assert result["routes"]["type"] == "FeatureCollection"


def test_weather_stations_near_shape_without_db(no_db):
    result = weather_stations_near(lat=40.7, lon=-74.0, radius_km=100)
    assert result["tool"] == "weather_stations_near"
    assert result["count"] == 0
    assert "NOAA" in result["explanation"]


def test_stream_gauges_near_shape_without_db(no_db):
    result = stream_gauges_near(lat=40.7, lon=-74.0, radius_km=100)
    assert result["tool"] == "stream_gauges_near"
    assert result["count"] == 0
    assert "USGS" in result["explanation"]


def test_routes_near_shape_without_db(no_db):
    result = routes_near(lat=40.7, lon=-74.0, radius_km=25)
    assert result["tool"] == "routes_near"
    assert result["count"] == 0
    assert "route" in result["explanation"]


def test_entities_in_bbox_shape_without_db(no_db):
    result = entities_in_bbox(min_lon=-74.5, min_lat=40.5, max_lon=-73.5, max_lat=41.0)
    assert result["tool"] == "entities_in_bbox"
    assert result["count"] == 0
    assert "-74.500" in result["explanation"]


def test_entities_in_bbox_with_entity_type_without_db(no_db):
    result = entities_in_bbox(
        min_lon=-74.5, min_lat=40.5, max_lon=-73.5, max_lat=41.0, entity_type="port"
    )
    assert "(port)" in result["explanation"]


def test_search_entities_shape_without_db(no_db):
    result = search_entities(q="newark")
    assert result["tool"] == "search_entities"
    assert result["count"] == 0
    assert "newark" in result["explanation"]


def test_search_entities_with_type_filter_without_db(no_db):
    result = search_entities(q="port", entity_type="port")
    assert "(port)" in result["explanation"]


def test_gis_metadata_describes_crs_and_units():
    result = gis_metadata()
    assert result["tool"] == "gis_metadata"
    assert result["metadata"]["crs"]["epsg"] == "EPSG:4326"
    assert result["metadata"]["coordinate_order"] == ["longitude", "latitude"]
    assert result["metadata"]["geometry_format"] == "GeoJSON"


def test_layer_metadata_shape_without_db(no_db):
    result = layer_metadata()
    assert result["tool"] == "layer_metadata"
    assert result["layer_count"] == 0
    assert result["layers"] == []
    assert result["metadata"]["crs"]["srid"] == 4326


def test_topology_relations_for_entity_shape_without_db(no_db):
    result = topology_relations_for_entity(entity_id="asset-1", relation="intersects")
    assert result["tool"] == "topology_relations_for_entity"
    assert result["type"] == "FeatureCollection"
    assert result["parameters"]["relation"] == "intersects"
    assert result["metadata"]["topology_engine"] == "PostGIS"


def test_buffer_entity_shape_without_db(no_db):
    result = buffer_entity(entity_id="asset-1", distance_m=500)
    assert result["tool"] == "buffer_entity"
    assert result["type"] == "FeatureCollection"
    assert result["parameters"]["distance_m"] == 500
    assert result["metadata"]["crs"] == "EPSG:4326"


def test_assets_impacted_by_event_shape_without_db(no_db):
    result = assets_impacted_by_event(event_id="risk-1")
    assert result["tool"] == "assets_impacted_by_event"
    assert result["type"] == "FeatureCollection"
    assert result["count"] == 0


def test_risk_events_near_asset_shape_without_db(no_db):
    result = risk_events_near_asset(entity_id="asset-1")
    assert result["tool"] == "risk_events_near_asset"
    assert result["type"] == "FeatureCollection"
    assert result["count"] == 0


def test_routes_impacted_by_alert_shape_without_db(no_db):
    result = routes_impacted_by_alert(event_id="risk-1")
    assert result["tool"] == "routes_impacted_by_alert"
    assert result["type"] == "FeatureCollection"
    assert result["count"] == 0


def test_summarize_asset_exposure_shape_without_db(no_db):
    result = summarize_asset_exposure(entity_id="asset-1")
    assert result["tool"] == "summarize_asset_exposure"
    assert result["type"] == "FeatureCollection"
    assert result["count"] == 0


# ---------------------------------------------------------------------------
# Tool result structure — shared contract
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "tool",
    "parameters",
    "count",
    "type",
    "features",
    "sources",
    "explanation",
    "confidence",
}


def test_all_tools_return_required_keys(no_db):
    results = [
        ports_near(lat=40.7, lon=-74.0),
        facilities_near(lat=40.7, lon=-74.0),
        weather_stations_near(lat=40.7, lon=-74.0),
        stream_gauges_near(lat=40.7, lon=-74.0),
        routes_near(lat=40.7, lon=-74.0),
        entities_in_bbox(min_lon=-74.5, min_lat=40.5, max_lon=-73.5, max_lat=41.0),
        search_entities(q="test"),
        assets_impacted_by_event(event_id="risk-1"),
        risk_events_near_asset(entity_id="asset-1"),
        routes_impacted_by_alert(event_id="risk-1"),
        summarize_asset_exposure(entity_id="asset-1"),
        topology_relations_for_entity(entity_id="asset-1"),
        buffer_entity(entity_id="asset-1"),
    ]
    for result in results:
        assert REQUIRED_KEYS.issubset(result.keys()), f"Missing keys in {result['tool']}"
        assert result["type"] == "FeatureCollection"
        assert isinstance(result["features"], list)
        assert isinstance(result["sources"], list)
        assert 0.0 <= result["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Integration tests — real PostGIS (skipped when DB unavailable)
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_port():
    """Insert a known port into PostGIS, yield its metadata, clean up after."""
    from pipelines.db import db_connection

    try:
        with db_connection() as probe:
            probe.execute("SELECT 1")
    except Exception as exc:
        pytest.skip(f"PostGIS unavailable: {exc}")

    token = uuid4().hex
    source_entity_id = f"pytest_tools/{token}"

    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO sources (name, api_url, auth_required, refresh_rate, metadata)
            VALUES ('pytest_tools', '', false, 'never', '{}'::jsonb)
            ON CONFLICT (name) DO NOTHING
            """
        )
        source_id = conn.execute("SELECT id FROM sources WHERE name = 'pytest_tools'").fetchone()[
            "id"
        ]
        conn.execute(
            """
            INSERT INTO geo_entities
              (entity_type, subtype, name, description, geometry, source_id, source_name,
               source_entity_id, source_tags, confidence)
            VALUES ('port', null, 'Pytest Tool Test Port', null,
                    ST_SetSRID(ST_MakePoint(-74.0, 40.7), 4326),
                    %s, 'pytest_tools', %s, '{}'::jsonb, 0.9)
            ON CONFLICT (source_name, source_entity_id, entity_type) DO NOTHING
            """,
            (source_id, source_entity_id),
        )
        conn.commit()

    yield {
        "source_entity_id": source_entity_id,
        "name": "Pytest Tool Test Port",
        "lat": 40.7,
        "lon": -74.0,
    }

    with db_connection() as conn:
        conn.execute(
            "DELETE FROM geo_entities WHERE source_name = 'pytest_tools' AND source_entity_id = %s",
            (source_entity_id,),
        )
        conn.execute(
            """
            DELETE FROM sources
            WHERE name = 'pytest_tools'
              AND NOT EXISTS (
                SELECT 1 FROM geo_entities WHERE source_id = sources.id
              )
            """
        )
        conn.commit()


def test_ports_near_real_db(seeded_port):
    result = ports_near(lat=seeded_port["lat"], lon=seeded_port["lon"], radius_km=1)
    names = {f["properties"]["name"] for f in result["features"]}
    assert seeded_port["name"] in names
    hit = next(f for f in result["features"] if f["properties"]["name"] == seeded_port["name"])
    assert hit["properties"]["distance_km"] < 0.01  # same point
    assert result["count"] > 0
    assert result["sources"]


def test_search_entities_real_db(seeded_port):
    result = search_entities(q="Pytest Tool Test Port")
    names = {f["properties"]["name"] for f in result["features"]}
    assert seeded_port["name"] in names
    assert result["count"] > 0


def test_entities_in_bbox_real_db(seeded_port):
    result = entities_in_bbox(
        min_lon=-74.05, min_lat=40.65, max_lon=-73.95, max_lat=40.75, entity_type="port"
    )
    names = {f["properties"]["name"] for f in result["features"]}
    assert seeded_port["name"] in names
    assert result["count"] > 0
