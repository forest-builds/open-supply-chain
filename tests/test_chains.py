from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from api.chains import connected, entity_routes, refrigerated_food_port_newark_chain
from api.tools import (
    example_refrigerated_food_port_newark,
    find_chain_assets,
    trace_supply_chain,
)
from pipelines.chain_network import build_chain_network


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _EmptyDB:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_, **__):
        return self

    def fetchall(self):
        return []

    def fetchone(self):
        return {"count": 0}


class _BrokenDB:
    def __enter__(self):
        raise psycopg.OperationalError("db unavailable")

    def __exit__(self, *_):
        return False


@pytest.fixture()
def no_db(monkeypatch):
    monkeypatch.setattr("api.chains.get_connection", lambda: _BrokenDB())
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())


# ---------------------------------------------------------------------------
# 1. Pipeline SQL sanity
# ---------------------------------------------------------------------------

import pipelines.chain_network as _cn  # noqa: E402


def test_pipeline_sql_contains_st_dwithin():
    src = open(_cn.__file__).read()
    assert "ST_DWithin" in src
    assert "SERVED_BY_ROUTE" in src
    assert "ON CONFLICT" in src
    assert "DO NOTHING" in src


# ---------------------------------------------------------------------------
# 2. build_chain_network returns edge count
# ---------------------------------------------------------------------------


def test_build_chain_network_returns_count():
    class FakeConn:
        def execute(self, sql, params=None):
            self._last_sql = sql
            return self

        def fetchone(self):
            return {"count": 42}

    count = build_chain_network(FakeConn(), source_id="fake-source-id", distance_m=500)
    assert count == 42


# ---------------------------------------------------------------------------
# 3. /chains/connected — shape test without DB
# ---------------------------------------------------------------------------


def test_connected_endpoint_no_db(no_db):
    result = connected(entity_id=str(uuid.uuid4()), limit=10)
    assert result["type"] == "FeatureCollection"
    assert result["count"] == 0
    assert result["features"] == []
    assert "entity_id" in result
    assert "explanation" in result


# ---------------------------------------------------------------------------
# 4. /chains/routes — shape test without DB
# ---------------------------------------------------------------------------


def test_entity_routes_no_db(no_db):
    result = entity_routes(entity_id=str(uuid.uuid4()))
    assert result["type"] == "FeatureCollection"
    assert result["count"] == 0
    assert result["features"] == []


# ---------------------------------------------------------------------------
# 5. /chains/summary — returns expected keys without DB
# ---------------------------------------------------------------------------


def test_chain_summary_no_db(monkeypatch):
    monkeypatch.setattr("api.chains.get_connection", lambda: _BrokenDB())
    from api.chains import chain_summary

    result = chain_summary()
    assert "total_edges" in result
    assert "node_count" in result
    assert "route_count" in result
    assert result["total_edges"] == 0


# ---------------------------------------------------------------------------
# 6. trace_supply_chain tool — shape + "corridor" in explanation
# ---------------------------------------------------------------------------


def test_trace_supply_chain_shape(monkeypatch):
    monkeypatch.setattr("api.chains.get_connection", lambda: _BrokenDB())
    result = trace_supply_chain(entity_id=str(uuid.uuid4()), limit=10)
    assert result["tool"] == "trace_supply_chain"
    assert result["type"] == "FeatureCollection"
    assert result["count"] == 0
    assert "corridor" in result["explanation"]


# ---------------------------------------------------------------------------
# 7. find_chain_assets — "No entity" message when search returns 0
# ---------------------------------------------------------------------------


def test_find_chain_assets_not_found(monkeypatch):
    monkeypatch.setattr("api.chains.get_connection", lambda: _BrokenDB())
    monkeypatch.setattr("api.tools.get_connection", lambda: _BrokenDB())
    result = find_chain_assets(name="nonexistent-xyz-facility", entity_type="port", limit=5)
    assert result["tool"] == "find_chain_assets"
    assert result["count"] == 0
    assert "No entity" in result["explanation"]


# ---------------------------------------------------------------------------
# 8. Concrete chain example — refrigerated food through Port Newark
# ---------------------------------------------------------------------------


def test_refrigerated_food_port_newark_no_db(no_db):
    result = refrigerated_food_port_newark_chain()

    assert result["slug"] == "refrigerated-food-imports-port-newark"
    assert result["anchor_port"] is None
    assert result["routes"]["count"] == 0
    assert result["facilities"]["count"] == 0
    assert result["vessels"]["count"] == 0
    assert "EIA petroleum terminals" in " ".join(result["limitations"])


def test_refrigerated_food_port_newark_with_evidence(monkeypatch):
    port_id = str(uuid.uuid4())
    route_id = str(uuid.uuid4())

    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, params=None):
            if "entity_type = 'port'" in sql:
                return FakeResult([
                    {
                        "id": port_id,
                        "entity_type": "port",
                        "subtype": "port",
                        "name": "Port Newark",
                        "source_name": "osm",
                        "confidence": 0.9,
                        "source_tags": {"name": "Port Newark"},
                        "geometry": {"type": "Point", "coordinates": [-74.15, 40.68]},
                    }
                ])
            if "relationship_confidence" in sql:
                return FakeResult([
                    {
                        "id": route_id,
                        "entity_type": "route",
                        "subtype": "highway",
                        "name": "I-95",
                        "source_name": "osm",
                        "confidence": 0.9,
                        "source_tags": {"ref": "I 95"},
                        "relationship_confidence": 0.8,
                        "geometry": {"type": "LineString", "coordinates": [[-74.16, 40.68], [-74.1, 40.7]]},
                    }
                ])
            if "cold-chain keyword match" in sql:
                return FakeResult([
                    {
                        "id": str(uuid.uuid4()),
                        "entity_type": "facility",
                        "subtype": "warehouse",
                        "name": "Newark Cold Storage",
                        "source_name": "osm",
                        "confidence": 0.8,
                        "source_tags": {"building": "warehouse"},
                        "via_route_id": route_id,
                        "via_route_name": "I-95",
                        "via_route_subtype": "highway",
                        "chain_confidence": 0.7,
                        "evidence_label": "cold-chain keyword match",
                        "geometry": {"type": "Point", "coordinates": [-74.12, 40.69]},
                    }
                ])
            if "ais_vessels" in sql:
                return FakeResult([
                    {
                        "id": str(uuid.uuid4()),
                        "entity_type": "location",
                        "subtype": "vessel",
                        "name": "REEFER EXAMPLE",
                        "source_name": "ais_vessels",
                        "confidence": 0.85,
                        "source_tags": {"ship_type": "cargo", "destination": "NEWARK"},
                        "distance_m": 1200.0,
                        "geometry": {"type": "Point", "coordinates": [-74.14, 40.67]},
                    }
                ])
            return FakeResult([])

    monkeypatch.setattr("api.chains.get_connection", lambda: FakeConn())

    result = refrigerated_food_port_newark_chain(radius_km=8, limit=5)
    tool_result = example_refrigerated_food_port_newark(radius_km=8, limit=5)

    assert result["anchor_port"]["properties"]["name"] == "Port Newark"
    assert result["routes"]["count"] == 1
    assert result["facilities"]["features"][0]["properties"]["evidence_label"] == "cold-chain keyword match"
    assert result["vessels"]["features"][0]["properties"]["source_tags"]["ship_type"] == "cargo"
    assert result["evidence_count"] == 4
    assert tool_result["tool"] == "example_refrigerated_food_port_newark"


# ---------------------------------------------------------------------------
# 9. Admin endpoint — schedules task, returns pipeline key
# ---------------------------------------------------------------------------


def test_admin_chain_network_endpoint():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    # We don't actually run the background task; just verify the response shape
    resp = client.post("/admin/ingest/chain-network")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["pipeline"] == "chain-network"


# ---------------------------------------------------------------------------
# 10. Integration — seed port + route, build edges, assert ≥1 SERVED_BY_ROUTE
# ---------------------------------------------------------------------------

DB_URL = os.environ.get("DATABASE_URL", "")


@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")
def test_integration_build_chain_network():
    import psycopg
    from psycopg.rows import dict_row

    port_id = str(uuid.uuid4())
    route_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    source_name = f"test_chain_src_{source_id}"

    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        # Seed a minimal source row
        conn.execute(
            """
            INSERT INTO sources (id, name, api_url, auth_required, refresh_rate, metadata)
            VALUES (%s, %s, 'test://', false, 'manual', '{}')
            ON CONFLICT DO NOTHING
            """,
            (source_id, source_name),
        )
        # Seed port at KEARNY, NJ
        conn.execute(
            """
            INSERT INTO geo_entities
              (id, entity_type, subtype, name, source_id, source_name, source_entity_id, confidence, geometry)
            VALUES (%s, 'port', 'port', 'Test Port Kearny', %s, 'test', %s, 0.9,
                    ST_SetSRID(ST_MakePoint(-74.145, 40.751), 4326))
            ON CONFLICT DO NOTHING
            """,
            (port_id, source_id, port_id),
        )
        # Seed a short route segment ~200m away
        conn.execute(
            """
            INSERT INTO geo_entities
              (id, entity_type, subtype, name, source_id, source_name, source_entity_id, confidence, geometry)
            VALUES (%s, 'route', 'highway', 'Test Route NJ', %s, 'test', %s, 0.9,
                    ST_SetSRID(ST_MakeLine(ST_MakePoint(-74.145, 40.750), ST_MakePoint(-74.146, 40.752)), 4326))
            ON CONFLICT DO NOTHING
            """,
            (route_id, source_id, route_id),
        )
        conn.commit()

        try:
            count = build_chain_network(conn, source_id, distance_m=500)
            conn.commit()
            assert count >= 1, f"Expected ≥1 SERVED_BY_ROUTE edge, got {count}"
        finally:
            conn.execute(
                """
                DELETE FROM entity_relationships
                WHERE source_id = %s
                   OR subject_entity_id IN (
                     SELECT id FROM geo_entities WHERE source_id = %s
                   )
                   OR object_entity_id IN (
                     SELECT id FROM geo_entities WHERE source_id = %s
                   )
                """,
                (source_id, source_id, source_id),
            )
            conn.execute("DELETE FROM geo_entities WHERE source_id = %s", (source_id,))
            conn.execute("DELETE FROM sources WHERE id = %s", (source_id,))
            conn.commit()
