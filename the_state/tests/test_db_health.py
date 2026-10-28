"""DB health route. Requires a running Postgres (see conftest.py)."""

import pytest


@pytest.mark.asyncio
async def test_db_health(client):
    resp = await client.get("/db/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"
