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
    }
