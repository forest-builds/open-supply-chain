from uuid import uuid4

import psycopg
import pytest

from pipelines.db import db_connection
from pipelines.osm import (
    insert_raw_ingestion,
    load_contract,
    upsert_aoi,
    upsert_geo_entities,
    upsert_source,
)


def require_postgis_connection():
    try:
        connection_context = db_connection()
        conn = connection_context.__enter__()
    except (RuntimeError, psycopg.OperationalError) as exc:
        pytest.skip(f"PostGIS is not available: {exc}")
    return connection_context, conn


def test_osm_upsert_pipeline_writes_raw_and_canonical_records() -> None:
    connection_context, conn = require_postgis_connection()
    test_token = uuid4().hex
    ingestion_key = f"pytest_{test_token}"
    source_entity_id = f"pytest/{test_token}"

    try:
        contract = load_contract()
        source_id = upsert_source(conn, contract)
        upsert_aoi(conn)

        payload = {
            "elements": [
                {
                    "type": "node",
                    "id": test_token,
                    "lat": 40.7,
                    "lon": -74.0,
                    "tags": {"amenity": "ferry_terminal", "name": "Pytest Ferry Terminal"},
                }
            ]
        }
        insert_raw_ingestion(
            conn,
            source_id,
            ingestion_key,
            {"test": True},
            payload,
        )
        upsert_geo_entities(
            conn,
            source_id,
            [
                {
                    "entity_type": "port",
                    "subtype": None,
                    "name": "Pytest Ferry Terminal",
                    "description": None,
                    "geometry": {"type": "Point", "coordinates": [-74.0, 40.7]},
                    "source_name": "openstreetmap",
                    "source_entity_id": source_entity_id,
                    "source_tags": {"amenity": "ferry_terminal", "name": "Pytest Ferry Terminal"},
                    "confidence": 0.7,
                }
            ],
        )
        conn.commit()

        raw_count = conn.execute(
            "SELECT count(*) FROM raw_ingestions WHERE ingestion_key = %s",
            (ingestion_key,),
        ).fetchone()["count"]
        entity = conn.execute(
            """
            SELECT entity_type, subtype, name, source_tags, ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo_entities
            WHERE source_name = 'openstreetmap' AND source_entity_id = %s
            """,
            (source_entity_id,),
        ).fetchone()

        assert raw_count == 1
        assert entity["entity_type"] == "port"
        assert entity["subtype"] is None
        assert entity["name"] == "Pytest Ferry Terminal"
        assert entity["source_tags"]["amenity"] == "ferry_terminal"
        assert entity["geometry"]["type"] == "Point"
    finally:
        conn.execute(
            "DELETE FROM geo_entities WHERE source_name = 'openstreetmap' AND source_entity_id = %s",
            (source_entity_id,),
        )
        conn.execute("DELETE FROM raw_ingestions WHERE ingestion_key = %s", (ingestion_key,))
        conn.commit()
        connection_context.__exit__(None, None, None)
