"""MCP server productionization (Task 1.1). No DB required."""

from __future__ import annotations

import pytest
from mcp_server import build_server


@pytest.mark.asyncio
async def test_server_registers_all_tools():
    server = build_server(base_url="http://127.0.0.1:9")
    tools = {t.name for t in await server.list_tools()}
    assert tools == {
        "get_current_state",
        "generate_operational_brief",
        "watch_entity",
        "health_check",
    }


@pytest.mark.asyncio
async def test_get_current_state_tool_has_place_schema():
    server = build_server()
    tool = next(t for t in await server.list_tools() if t.name == "get_current_state")
    assert tool.inputSchema["properties"]["place"]["type"] == "string"


@pytest.mark.asyncio
async def test_tool_returns_structured_error_when_api_unreachable():
    # Delegates to the real client; with no API up it must not raise, it must
    # return a structured error the agent can reason about.
    server = build_server(base_url="http://127.0.0.1:1")
    result = await server.call_tool("get_current_state", {"place": "New York, NY"})
    payload = result[1] if isinstance(result, tuple) else result
    assert isinstance(payload, dict)
    assert payload.get("error") in {"api_unreachable", "internal_error"}


@pytest.mark.asyncio
async def test_health_check_reports_unhealthy_when_api_down():
    server = build_server(base_url="http://127.0.0.1:1")
    result = await server.call_tool("health_check", {})
    payload = result[1] if isinstance(result, tuple) else result
    assert payload["status"] == "unhealthy"
