"""Source CRUD. Requires a running Postgres (see conftest.py)."""

import pytest


@pytest.mark.asyncio
async def test_list_sources_empty(client):
    resp = await client.get("/sources/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_create_source(client):
    payload = {
        "name": "openfema-test",
        "source_type": "openfema",
        "base_url": "https://www.fema.gov/api/open/v2",
        "description": "OpenFEMA disaster declarations",
        "meta": {"version": "v2"},
    }
    resp = await client.post("/sources/", json=payload)
    assert resp.status_code == 201

    data = resp.json()
    assert data["name"] == "openfema-test"
    assert data["source_type"] == "openfema"
    assert data["base_url"] == "https://www.fema.gov/api/open/v2"
    assert data["meta"] == {"version": "v2"}
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_sources_after_create(client):
    await client.post(
        "/sources/",
        json={"name": "noaa-test", "source_type": "noaa"},
    )
    resp = await client.get("/sources/")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["items"]}
    assert "noaa-test" in names


@pytest.mark.asyncio
async def test_create_source_duplicate_name(client):
    body = {"name": "dup-source", "source_type": "manual"}
    await client.post("/sources/", json=body)
    resp = await client.post("/sources/", json=body)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_source_minimal(client):
    resp = await client.post(
        "/sources/",
        json={"name": "bare-minimum", "source_type": "api"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["base_url"] is None
    assert data["description"] is None
    assert data["meta"] == {}
