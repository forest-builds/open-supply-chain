"""Runnable MCP server for The State.

Exposes the deterministic LocationState / brief / watchlist surfaces as MCP
tools that agent frameworks (Claude Desktop, Cursor, open-source runtimes)
connect to. It is a thin protocol shell over ``TheStateMcpClient`` — all logic
lives behind the API; this process never scores anything itself.

Run it::

    uv run the-state-mcp                       # stdio (Claude Desktop / Cursor)
    THE_STATE_MCP_TRANSPORT=streamable-http \\
        uv run the-state-mcp                   # HTTP (containers)

Config via env: ``THE_STATE_API_URL`` (default http://localhost:8000),
``THE_STATE_MCP_TRANSPORT`` (stdio|sse|streamable-http),
``THE_STATE_MCP_HOST``/``THE_STATE_MCP_PORT`` for HTTP transports.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from mcp_server.client import TheStateMcpClient
from mcp_server.tools import (
    GenerateOperationalBriefInput,
    GetCurrentStateInput,
    WatchEntityInput,
)

logger = logging.getLogger("the_state.mcp")


def _api_base_url() -> str:
    return os.environ.get("THE_STATE_API_URL", "http://localhost:8000")


def _format_error(tool: str, exc: Exception) -> dict[str, Any]:
    """Never leak a stack trace to the agent; return a structured error."""
    if isinstance(exc, httpx.HTTPStatusError):
        detail: Any
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        logger.warning("%s failed: HTTP %s", tool, exc.response.status_code)
        return {
            "error": "upstream_error",
            "status_code": exc.response.status_code,
            "detail": detail,
        }
    if isinstance(exc, httpx.HTTPError):
        logger.warning("%s failed: connection error: %s", tool, exc)
        return {"error": "api_unreachable", "detail": str(exc)}
    logger.exception("%s failed: unexpected error", tool)
    return {"error": "internal_error", "detail": str(exc)}


def build_server(*, base_url: str | None = None) -> FastMCP:
    """Construct the FastMCP server with all tools registered.

    Factored out so tests can introspect the registered tools without
    starting an event loop.
    """
    api_url = base_url or _api_base_url()
    mcp = FastMCP("the-state")

    def _client() -> TheStateMcpClient:
        return TheStateMcpClient(base_url=api_url)

    @mcp.tool(
        name="get_current_state",
        description="Return current deterministic LocationState for a place.",
    )
    async def get_current_state(place: str, time_window: str = "24h") -> dict[str, Any]:
        payload = GetCurrentStateInput(place=place, time_window=time_window)
        try:
            async with _client() as c:
                return await c.get_current_state(payload)
        except Exception as exc:  # noqa: BLE001 - boundary: structured error out
            return _format_error("get_current_state", exc)

    @mcp.tool(
        name="generate_operational_brief",
        description="Generate a deterministic operational brief from state/provenance.",
    )
    async def generate_operational_brief(
        watchlist_id: str | None = None,
        watched_entity_id: str | None = None,
        evaluation_result_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            payload = GenerateOperationalBriefInput(
                watchlist_id=watchlist_id,
                watched_entity_id=watched_entity_id,
                evaluation_result_id=evaluation_result_id,
            )
            async with _client() as c:
                return await c.generate_operational_brief(payload)
        except Exception as exc:  # noqa: BLE001
            return _format_error("generate_operational_brief", exc)

    @mcp.tool(
        name="watch_entity",
        description="Create a location watchlist for repeated evaluation.",
    )
    async def watch_entity(
        name: str,
        place: str,
        time_window: str = "24h",
        thresholds: dict[str, Any] | None = None,
        delivery: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            payload = WatchEntityInput(
                name=name,
                place=place,
                time_window=time_window,
                thresholds=thresholds,
                delivery=delivery,
            )
            async with _client() as c:
                return await c.watch_entity(payload)
        except Exception as exc:  # noqa: BLE001
            return _format_error("watch_entity", exc)

    @mcp.tool(
        name="health_check",
        description="Check that the backing The State API is reachable.",
    )
    async def health_check() -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=api_url, timeout=5.0) as http:
                resp = await http.get("/health")
                resp.raise_for_status()
            return {"status": "ok", "api_url": api_url}
        except Exception as exc:  # noqa: BLE001
            return {"status": "unhealthy", **_format_error("health_check", exc)}

    return mcp


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("THE_STATE_MCP_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    transport = os.environ.get("THE_STATE_MCP_TRANSPORT", "stdio")
    server = build_server()
    if transport in ("sse", "streamable-http"):
        server.settings.host = os.environ.get("THE_STATE_MCP_HOST", "0.0.0.0")
        server.settings.port = int(os.environ.get("THE_STATE_MCP_PORT", "8765"))
    logger.info(
        "Starting The State MCP server (transport=%s, api=%s)",
        transport,
        _api_base_url(),
    )
    server.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
