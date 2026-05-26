import asyncio

import psycopg

from api import mcp_server


class _BrokenDB:
    def __enter__(self):
        raise psycopg.OperationalError("db unavailable")

    def __exit__(self, *args):
        return False


def test_mcp_spatial_tools_return_existing_tool_contract(monkeypatch):
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())

    results = [
        mcp_server.ports_near(lat=40.7, lon=-74.0, radius_km=50),
        mcp_server.facilities_near(lat=40.7, lon=-74.0, radius_km=30, subtype="warehouse"),
        mcp_server.weather_stations_near(lat=40.7, lon=-74.0),
        mcp_server.stream_gauges_near(lat=40.7, lon=-74.0),
        mcp_server.routes_near(lat=40.7, lon=-74.0),
    ]

    assert [result["tool"] for result in results] == [
        "ports_near",
        "facilities_near",
        "weather_stations_near",
        "stream_gauges_near",
        "routes_near",
    ]
    for result in results:
        assert result["type"] == "FeatureCollection"
        assert result["parameters"]["lat"] == 40.7
        assert result["parameters"]["lon"] == -74.0


def test_mcp_bbox_and_search_forward_optional_filters(monkeypatch):
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())

    bbox = mcp_server.entities_in_bbox(
        min_lon=-74.5,
        min_lat=40.5,
        max_lon=-73.5,
        max_lat=41.0,
        entity_type="port",
    )
    search = mcp_server.search_entities(q="newark", entity_type="port")

    assert bbox["tool"] == "entities_in_bbox"
    assert bbox["parameters"]["entity_type"] == "port"
    assert search["tool"] == "search_entities"
    assert search["parameters"]["entity_type"] == "port"


def test_mcp_gis_metadata_tools(monkeypatch):
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())

    gis = mcp_server.gis_metadata()
    layers = mcp_server.layer_metadata()

    assert gis["metadata"]["crs"]["epsg"] == "EPSG:4326"
    assert layers["tool"] == "layer_metadata"
    assert layers["layers"] == []


def test_mcp_topology_tools_return_existing_tool_contract(monkeypatch):
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())

    relations = mcp_server.topology_relations_for_entity(
        entity_id="asset-1",
        relation="intersects",
        entity_type="route",
    )
    buffer = mcp_server.buffer_entity(entity_id="asset-1", distance_m=1000)

    assert relations["tool"] == "topology_relations_for_entity"
    assert relations["parameters"]["entity_type"] == "route"
    assert relations["metadata"]["topology_engine"] == "PostGIS"
    assert buffer["tool"] == "buffer_entity"
    assert buffer["metadata"]["crs"] == "EPSG:4326"


def test_mcp_chain_example_tool(monkeypatch):
    monkeypatch.setattr("api.chains.get_connection", lambda: _BrokenDB())

    result = mcp_server.example_refrigerated_food_port_newark()

    assert result["tool"] == "example_refrigerated_food_port_newark"
    assert result["slug"] == "refrigerated-food-imports-port-newark"
    assert "anchor_port" in result


def test_mcp_geocode_uses_existing_geocoder(monkeypatch):
    monkeypatch.setattr(
        "api.mcp_server._geocode",
        lambda query: {"lat": 40.7, "lon": -74.0, "display_name": query},
    )

    result = mcp_server.geocode("Port Newark")

    assert result == {"lat": 40.7, "lon": -74.0, "display_name": "Port Newark"}


def test_mcp_alert_tools_return_existing_tool_contract(monkeypatch):
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())

    active = mcp_server.active_alerts_near(lat=40.7, lon=-74.0, radius_km=100)
    nearby = mcp_server.risk_events_near(lat=40.7, lon=-74.0, radius_km=100, source="noaa_nws_alerts")
    vessels = mcp_server.vessels_near(lat=40.7, lon=-74.0, radius_km=25)

    assert active["tool"] == "active_alerts_near"
    assert active["type"] == "FeatureCollection"
    assert nearby["tool"] == "risk_events_near"
    assert nearby["parameters"]["source"] == "noaa_nws_alerts"
    assert vessels["tool"] == "vessels_near"
    assert vessels["parameters"]["lat"] == 40.7


def test_mcp_corridor_risk_and_chain_tools(monkeypatch):
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())
    monkeypatch.setattr("api.chains.get_connection", lambda: _BrokenDB())

    corridor = mcp_server.corridor_risk_exposure(entity_id="asset-1")
    chain = mcp_server.trace_supply_chain(entity_id="asset-1")
    chain_by_name = mcp_server.find_chain_assets(name="Port Newark", entity_type="port")
    exposure = mcp_server.summarize_asset_exposure(entity_id="asset-1")

    assert corridor["tool"] == "corridor_risk_exposure"
    assert corridor["type"] == "FeatureCollection"
    assert corridor["anchor"]["entity_id"] == "asset-1"
    assert chain["tool"] == "trace_supply_chain"
    assert chain_by_name["tool"] == "find_chain_assets"
    assert exposure["tool"] == "summarize_asset_exposure"


def test_mcp_impact_tools_return_existing_tool_contract(monkeypatch):
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())

    impacted = mcp_server.assets_impacted_by_event(event_id="event-1", entity_type="port")
    linked = mcp_server.risk_events_near_asset(entity_id="asset-1")

    assert impacted["tool"] == "assets_impacted_by_event"
    assert impacted["parameters"]["entity_type"] == "port"
    assert linked["tool"] == "risk_events_near_asset"


def test_mcp_server_instance_is_registerable():
    assert mcp_server.mcp.name == "Open Supply Chain"

    tools = asyncio.run(mcp_server.mcp.list_tools())
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "geocode",
        "ports_near",
        "facilities_near",
        "weather_stations_near",
        "stream_gauges_near",
        "routes_near",
        "entities_in_bbox",
        "search_entities",
        "gis_metadata",
        "layer_metadata",
        "topology_relations_for_entity",
        "buffer_entity",
        "example_refrigerated_food_port_newark",
        # impact network
        "risk_events_near_asset",
        "assets_impacted_by_event",
        "summarize_asset_exposure",
        # supply chain graph
        "trace_supply_chain",
        "find_chain_assets",
        # live alerting
        "active_alerts_near",
        "risk_events_near",
        # maritime
        "vessels_near",
        # network-level risk
        "corridor_risk_exposure",
    }
