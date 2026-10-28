from __future__ import annotations

from datetime import datetime, timezone

import pytest
from mcp_server import TheStateMcpClient, list_tool_schemas
from models.signal import Signal
from models.source import Source


async def _seed_source(db, name: str) -> Source:
    source = Source(name=name, source_type=name)
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def _seed_signal(
    db,
    *,
    source: Source,
    signal_type: str,
    severity: str,
    state_code: str = "NY",
) -> Signal:
    now = datetime.now(timezone.utc)
    signal = Signal(
        source_id=source.id,
        signal_type=signal_type,
        title=f"{signal_type} {severity}",
        severity=severity,
        observed_at=now,
        occurred_at=now,
        location={"state": state_code},
        attributes={},
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return signal


@pytest.mark.asyncio
async def test_mcp_client_uses_existing_state_watchlist_and_brief_surfaces(
    client,
    db_session,
):
    noaa = await _seed_source(db_session, "noaa")
    fema = await _seed_source(db_session, "openfema")
    await _seed_signal(
        db_session,
        source=noaa,
        signal_type="weather_alert",
        severity="Extreme",
    )
    await _seed_signal(
        db_session,
        source=fema,
        signal_type="declaration",
        severity="Major Disaster",
    )

    mcp = TheStateMcpClient(http_client=client)
    state = await mcp.get_current_state(
        {"place": "New York, NY", "time_window": "24h"},
    )
    watchlist = await mcp.watch_entity(
        {"name": "NYC Agent Watch", "place": "New York, NY"},
    )
    brief = await mcp.generate_operational_brief({"watchlist_id": watchlist["id"]})

    assert state["operational_state"] == "watch"
    assert watchlist["place"] == "New York, NY"
    assert brief["place"] == "New York, NY"
    assert brief["operational_state"] == "watch"
    assert brief["url"] == f"http://test/briefs/{brief['id']}"


def test_mcp_tool_schemas_are_documented():
    schemas = list_tool_schemas()

    assert set(schemas) == {
        "generate_operational_brief",
        "get_current_state",
        "watch_entity",
    }
    assert schemas["get_current_state"]["input_schema"]["properties"]["place"]["type"] == "string"
    assert "watchlist_id" in schemas["generate_operational_brief"]["input_schema"]["properties"]
    assert "place" in schemas["watch_entity"]["input_schema"]["properties"]
