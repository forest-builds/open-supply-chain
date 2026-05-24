from __future__ import annotations

import json
import os
from typing import Any

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from api.tools import (
    entities_in_bbox,
    facilities_near,
    ports_near,
    routes_near,
    search_entities,
    stream_gauges_near,
    weather_stations_near,
)

chat_router = APIRouter(prefix="/tools", tags=["chat"])

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
OPENAI_MODEL = "gpt-4o-mini"
MAX_ROUNDS = 5
NOMINATIM_UA = "open-supply-chain/0.1"

SYSTEM = """\
You are a supply-chain intelligence assistant with access to deterministic geospatial tools \
that query a live PostGIS database covering the NY/NJ/CT tri-state supply chain.

The database contains: ports, facilities (warehouses, industrial sites, storage tanks), \
transport routes (highway, rail, ferry, waterway), NOAA weather stations, USGS stream/estuary/lake \
gauge sites, and active NWS weather alerts and USGS earthquake events as risk events.

Rules:
1. If the user mentions a place name or address, ALWAYS call geocode first to get lat/lon.
2. Call the most specific spatial tool that matches the request.
3. For flood, river, waterway, or water-level questions use stream_gauges_near.
4. Respond concisely — state how many results were found, the nearest entity, and any key details.
5. Do NOT list every entity name. Summarize instead.
6. If you cannot find useful results, say so clearly.\
"""

# Anthropic tool definitions (input_schema format)
TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "geocode",
        "description": (
            "Convert a place name or address to lat/lon coordinates using Nominatim. "
            "Call this before any spatial tool when the user mentions a location by name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Place name or address (e.g. 'Port Newark', 'Manhattan', 'JFK Airport')",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "ports_near",
        "description": "Find ports within a radius of a lat/lon point, ordered by distance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Center latitude"},
                "lon": {"type": "number", "description": "Center longitude"},
                "radius_km": {"type": "number", "description": "Search radius in km (default 50)"},
                "limit": {"type": "integer", "description": "Max results (default 100)"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "facilities_near",
        "description": "Find facilities (warehouses, storage tanks, industrial sites) within a radius.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radius_km": {"type": "number", "description": "Search radius in km (default 50)"},
                "subtype": {
                    "type": "string",
                    "description": "warehouse | storage_tank | logistics | industrial_site",
                },
                "limit": {"type": "integer"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "weather_stations_near",
        "description": "Find NOAA weather monitoring stations near a point.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radius_km": {"type": "number", "description": "Search radius in km (default 100)"},
                "limit": {"type": "integer"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "routes_near",
        "description": "Find transport routes (highway, rail, ferry, waterway) passing within a radius of a point.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radius_km": {"type": "number", "description": "Search radius in km (default 25)"},
                "limit": {"type": "integer"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "entities_in_bbox",
        "description": "Return all supply chain entities within a bounding box.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_lon": {"type": "number", "description": "Western edge"},
                "min_lat": {"type": "number", "description": "Southern edge"},
                "max_lon": {"type": "number", "description": "Eastern edge"},
                "max_lat": {"type": "number", "description": "Northern edge"},
                "entity_type": {
                    "type": "string",
                    "description": "port | facility | route | location | aoi",
                },
                "limit": {"type": "integer"},
            },
            "required": ["min_lon", "min_lat", "max_lon", "max_lat"],
        },
    },
    {
        "name": "stream_gauges_near",
        "description": "Find USGS stream/estuary/lake gauge sites near a point. Use for flood risk, waterway, or river queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radius_km": {"type": "number", "description": "Search radius in km (default 100)"},
                "limit": {"type": "integer"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "search_entities",
        "description": "Full-text search across entity names. Use when user asks about a specific named entity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search term (case-insensitive partial match)",
                },
                "entity_type": {
                    "type": "string",
                    "description": "port | facility | route | location | aoi",
                },
                "limit": {"type": "integer"},
            },
            "required": ["q"],
        },
    },
]

# OpenAI tool definitions — same schema, different wrapper
OPENAI_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": td["name"],
            "description": td["description"],
            "parameters": td["input_schema"],
        },
    }
    for td in TOOL_DEFS
]


def _geocode(query: str) -> dict[str, Any]:
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": NOMINATIM_UA},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as exc:
        return {"error": str(exc)}
    if not results:
        return {"error": f"No geocoding results for '{query}'"}
    r = results[0]
    return {"lat": float(r["lat"]), "lon": float(r["lon"]), "display_name": r["display_name"]}


def _run_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "geocode":
        return _geocode(args["query"])
    if name == "ports_near":
        return ports_near(**args)
    if name == "facilities_near":
        return facilities_near(**args)
    if name == "weather_stations_near":
        return weather_stations_near(**args)
    if name == "routes_near":
        return routes_near(**args)
    if name == "entities_in_bbox":
        return entities_in_bbox(**args)
    if name == "stream_gauges_near":
        return stream_gauges_near(**args)
    if name == "search_entities":
        return search_entities(**args)
    return {"error": f"Unknown tool: {name}"}


def _tool_summary(name: str, result: dict[str, Any]) -> str:
    """Concise summary for the LLM — not the full GeoJSON payload."""
    if name == "geocode":
        if "error" in result:
            return result["error"]
        return f"Geocoded to lat={result['lat']}, lon={result['lon']} ({result.get('display_name', '')})"
    explanation = result.get("explanation", "")
    count = result.get("count", 0)
    return f"{explanation} ({count} features returned to map.)"


def _not_configured() -> dict[str, Any]:
    return {
        "response": (
            "AI chat is not configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable it. "
            "You can still use the layer toggles to explore the map."
        ),
        "tool_used": None,
        "tool_result": None,
    }


# ---------------------------------------------------------------------------
# Provider loops
# ---------------------------------------------------------------------------


def _run_anthropic(api_key: str, messages_in: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError:
        return {
            "response": "anthropic package not installed.",
            "tool_used": None,
            "tool_result": None,
        }

    client = anthropic.Anthropic(api_key=api_key)
    messages = list(messages_in)
    last_tool_result: dict[str, Any] | None = None
    last_tool_name: str | None = None

    for _ in range(MAX_ROUNDS):
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM,
            tools=TOOL_DEFS,
            messages=messages,
        )
        tool_uses = [b for b in resp.content if b.type == "tool_use"]

        if not tool_uses or resp.stop_reason == "end_turn":
            text = " ".join(b.text for b in resp.content if hasattr(b, "text") and b.text).strip()
            return {
                "response": text or "Done.",
                "tool_used": last_tool_name,
                "tool_result": last_tool_result,
            }

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for tu in tool_uses:
            result = _run_tool(tu.name, tu.input)
            if tu.name != "geocode":
                last_tool_name = tu.name
                last_tool_result = result
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": _tool_summary(tu.name, result),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return {
        "response": "I've analyzed your query and plotted the results on the map.",
        "tool_used": last_tool_name,
        "tool_result": last_tool_result,
    }


def _run_openai(api_key: str, messages_in: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import openai  # noqa: PLC0415
    except ImportError:
        return {"response": "openai package not installed.", "tool_used": None, "tool_result": None}

    client = openai.OpenAI(api_key=api_key)
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}] + list(messages_in)
    last_tool_result: dict[str, Any] | None = None
    last_tool_name: str | None = None

    for _ in range(MAX_ROUNDS):
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=OPENAI_TOOL_DEFS,
            tool_choice="auto",
        )
        choice = resp.choices[0]
        msg = choice.message

        if not msg.tool_calls or choice.finish_reason == "stop":
            return {
                "response": msg.content or "Done.",
                "tool_used": last_tool_name,
                "tool_result": last_tool_result,
            }

        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = _run_tool(tc.function.name, args)
            if tc.function.name != "geocode":
                last_tool_name = tc.function.name
                last_tool_result = result
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _tool_summary(tc.function.name, result),
                }
            )

    return {
        "response": "I've analyzed your query and plotted the results on the map.",
        "tool_used": last_tool_name,
        "tool_result": last_tool_result,
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    active_layers: list[str] = []


@chat_router.post("/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    provider = os.environ.get("LLM_PROVIDER", "").lower()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if provider == "openai" or (not anthropic_key and openai_key):
        if not openai_key:
            return _not_configured()
        return _run_openai(openai_key, messages)

    if provider == "anthropic" or (anthropic_key and not openai_key) or anthropic_key:
        if not anthropic_key:
            return _not_configured()
        return _run_anthropic(anthropic_key, messages)

    return _not_configured()
