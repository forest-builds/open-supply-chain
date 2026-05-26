from __future__ import annotations

import json
import os
from typing import Any

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from api.tools import (
    assets_impacted_by_event,
    entities_in_bbox,
    facilities_near,
    find_chain_assets,
    ports_near,
    risk_events_near,
    risk_events_near_asset,
    routes_near,
    search_entities,
    stream_gauges_near,
    summarize_asset_exposure,
    trace_supply_chain,
    weather_stations_near,
)

chat_router = APIRouter(prefix="/tools", tags=["chat"])

ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o-mini"
MAX_ROUNDS = 8
NOMINATIM_UA = "open-supply-chain/0.1"

SYSTEM = """\
You are a supply-chain intelligence assistant with access to live geospatial tools \
backed by a PostGIS database covering the NY/NJ/CT tri-state supply chain.

## What's in the Database
- **Ports**: Marine cargo terminals (Port Newark-Elizabeth, Red Hook Container Terminal, etc.)
- **Facilities**: Warehouses, storage tanks, TRI industrial/chemical sites (~3,700 EPA-tracked), \
federal logistics/freight contractors (from USASpending.gov), EIA power plants and energy facilities
- **Routes**: Highway, rail, ferry, and waterway transportation corridors
- **Locations**: NOAA weather stations, USGS stream/lake gauges, AIS-tracked vessels
- **Risk Events**: Active NWS weather alerts, USGS earthquake reports, GDACS global disasters — \
pre-linked to supply chain assets via a persisted impact network (risk_impacts table)

## Impact Network
Risk events are pre-linked to assets via spatial edges (intersection, buffer distance). \
Use this network — NOT proximity — when reasoning about what's truly threatened vs. merely nearby.

## Multi-Step Reasoning Strategy
Chain tools to answer questions — tool results include entity IDs needed for follow-up calls:

1. **Named place** → always call `geocode` first to get lat/lon
2. **Find an entity by name** → `search_entities` returns ID + type
3. **What threatens this asset?** → `risk_events_near_asset(entity_id=<id>)` — uses impact network
4. **Full risk exposure summary** → `summarize_asset_exposure(entity_id=<id>)`
5. **What does this event affect?** → `assets_impacted_by_event(event_id=<id>)`
6. **What's connected via supply chain?** → `trace_supply_chain(entity_id=<id>)`
7. **Active events near a place** → `risk_events_near(lat, lon)` — spatial query on event geometry

Example chain for "Is Port Newark at risk?":
  search_entities("Port Newark") → get entity id → risk_events_near_asset(entity_id) → \
  report severity and event types found

## Tool Selection Rules
1. Always `geocode` first when user mentions a place name or address.
2. For "what's at risk" / "is X threatened": search_entities → risk_events_near_asset
3. For "what does this alert affect": risk_events_near → assets_impacted_by_event
4. For supply chain connectivity ("what's connected to X"): search_entities → trace_supply_chain
5. For flood/water level queries: stream_gauges_near
6. For broad area overview: entities_in_bbox or facilities_near

## Response Style
- Be specific: cite entity names, severity levels, event types, and distances from tool data
- For risk: lead with highest severity events first
- For chains: name the routes that connect assets
- Keep responses under 200 words unless detail is explicitly requested
- If no results: say so clearly and suggest a broader search\
"""

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

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
        "name": "search_entities",
        "description": (
            "Full-text search across entity names. Returns entity IDs needed for follow-up tools like "
            "risk_events_near_asset, summarize_asset_exposure, and trace_supply_chain. "
            "Use when user asks about a specific named entity."
        ),
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
    {
        "name": "risk_events_near_asset",
        "description": (
            "Return risk events (weather alerts, earthquakes, global disasters) linked to a specific "
            "supply chain asset via the pre-computed impact network. "
            "Use this AFTER search_entities to find what threatens a named port or facility."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "geo_entities.id UUID from search_entities"},
                "limit": {"type": "integer", "description": "Max results (default 100)"},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "summarize_asset_exposure",
        "description": (
            "Summarize all risk impacts linked to one asset — counts by severity and event type. "
            "Use for 'how exposed is X' questions after getting entity_id from search_entities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "geo_entities.id UUID"},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "risk_events_near",
        "description": (
            "Find active risk events whose geometry intersects a radius around a lat/lon point. "
            "Use for 'what alerts are active near X' or to discover events before drilling into impacts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Center latitude"},
                "lon": {"type": "number", "description": "Center longitude"},
                "radius_km": {"type": "number", "description": "Search radius in km (default 150)"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "assets_impacted_by_event",
        "description": (
            "Return ports, facilities, and routes linked to a risk event via impact edges. "
            "Use event IDs from risk_events_near or risk_events_near_asset to find the blast radius."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "risk_events.id UUID"},
                "entity_type": {"type": "string", "description": "port | facility | route"},
                "limit": {"type": "integer", "description": "Max results (default 500)"},
            },
            "required": ["event_id"],
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
        "description": "Find facilities (warehouses, storage tanks, industrial sites, power plants, contractors) within a radius.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radius_km": {"type": "number", "description": "Search radius in km (default 50)"},
                "subtype": {
                    "type": "string",
                    "description": "warehouse | storage_tank | logistics | industrial_site | tri_facility | power_plant | contractor",
                },
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
        "name": "trace_supply_chain",
        "description": (
            "Find ports and facilities sharing a transportation corridor with a given entity ID. "
            "Use when the user asks what assets are connected to or reachable from a specific entity by UUID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "geo_entities.id UUID"},
                "limit": {"type": "integer", "description": "Max results (default 30)"},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "find_chain_assets",
        "description": (
            "Search for a named port or facility by name, then return corridor-connected supply chain peers. "
            "Use when the user names a place and asks about its supply chain connections."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Partial name match for the anchor entity"},
                "entity_type": {"type": "string", "description": "port | facility (default: port)"},
                "limit": {"type": "integer", "description": "Max results (default 30)"},
            },
            "required": ["name"],
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
    if name == "trace_supply_chain":
        return trace_supply_chain(**args)
    if name == "find_chain_assets":
        return find_chain_assets(**args)
    if name == "risk_events_near_asset":
        return risk_events_near_asset(**args)
    if name == "risk_events_near":
        return risk_events_near(**args)
    if name == "assets_impacted_by_event":
        return assets_impacted_by_event(**args)
    if name == "summarize_asset_exposure":
        return summarize_asset_exposure(**args)
    return {"error": f"Unknown tool: {name}"}


def _tool_summary(name: str, result: dict[str, Any]) -> str:
    """Rich summary for the LLM — includes entity names, IDs, and risk details for multi-hop reasoning."""
    if name == "geocode":
        if "error" in result:
            return result["error"]
        return f"Geocoded to lat={result['lat']:.4f}, lon={result['lon']:.4f} ({result.get('display_name', '')})"

    if name == "summarize_asset_exposure":
        asset = result.get("asset") or {}
        total = result.get("count", 0)
        exposure = result.get("exposure_summary") or []
        asset_name = (asset.get("name") if isinstance(asset, dict) else None) or "unknown"
        if not total:
            return f"{asset_name} has no active risk impacts in the impact network."
        lines = [f"{asset_name} has {total} risk impact(s):"]
        for row in (exposure if isinstance(exposure, list) else [])[:6]:
            if isinstance(row, dict):
                lines.append(
                    f"  [{row.get('severity','?')}] {row.get('event_type','?')} "
                    f"via {row.get('impact_method','?')}: {row.get('count', 1)} event(s)"
                )
        return "\n".join(lines)

    count = result.get("count", 0)
    features = result.get("features") or []
    explanation = result.get("explanation", "")

    if name in ("search_entities", "ports_near", "facilities_near", "routes_near",
                "entities_in_bbox", "find_chain_assets", "trace_supply_chain",
                "weather_stations_near", "stream_gauges_near"):
        if not features:
            return f"{explanation} No results found."
        lines = [explanation]
        for f in features[:5]:
            p = f.get("properties") or {}
            fid = f.get("id") or "?"
            fname = p.get("name") or "unnamed"
            ftype = p.get("entity_type") or ""
            fsubtype = p.get("subtype") or ""
            dist = p.get("distance_km")
            dist_str = f" ({dist:.1f}km)" if dist is not None else ""
            type_str = f"[{ftype}/{fsubtype}]" if fsubtype else f"[{ftype}]"
            lines.append(f"  {type_str} {fname} (id={fid}){dist_str}")
        if count > 5:
            lines.append(f"  ...and {count - 5} more")
        return "\n".join(lines)

    if name in ("risk_events_near_asset", "risk_events_near"):
        if not features:
            return f"{explanation} No active risk events found in the impact network."
        lines = [explanation]
        for f in features[:6]:
            p = f.get("properties") or {}
            fid = f.get("id") or "?"
            severity = p.get("severity") or "?"
            event_type = p.get("event_type") or "event"
            headline = (p.get("headline") or "")[:90]
            method = p.get("impact_method") or ""
            method_str = f" via {method}" if method else ""
            lines.append(f"  [{severity}] {event_type}: {headline}{method_str} (id={fid})")
        if count > 6:
            lines.append(f"  ...and {count - 6} more")
        return "\n".join(lines)

    if name == "assets_impacted_by_event":
        if not features:
            return f"{explanation} No impacted assets found."
        lines = [explanation]
        for f in features[:6]:
            p = f.get("properties") or {}
            fid = f.get("id") or "?"
            fname = p.get("name") or "unnamed"
            ftype = p.get("entity_type") or ""
            dist_m = p.get("impact_distance_m")
            dist_str = f" ({dist_m/1000:.1f}km)" if dist_m is not None else ""
            lines.append(f"  [{ftype}] {fname} (id={fid}){dist_str}")
        if count > 6:
            lines.append(f"  ...and {count - 6} more")
        return "\n".join(lines)

    return f"{explanation} ({count} features returned to map.)" if explanation else f"{count} features returned to map."


def _merge_tool_results(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Merge multiple FeatureCollection tool results into one for the map."""
    if not results:
        return None
    if len(results) == 1:
        return results[0]
    all_features: list[dict[str, Any]] = []
    all_sources: set[str] = set()
    for r in results:
        all_features.extend(r.get("features") or [])
        all_sources.update(r.get("sources") or [])
    last = results[-1]
    return {
        **last,
        "features": all_features,
        "count": len(all_features),
        "sources": sorted(all_sources),
    }


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
    all_tool_results: list[dict[str, Any]] = []
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
                "tool_result": _merge_tool_results(all_tool_results),
            }

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for tu in tool_uses:
            result = _run_tool(tu.name, tu.input)
            if tu.name != "geocode":
                last_tool_name = tu.name
                all_tool_results.append(result)
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
        "tool_result": _merge_tool_results(all_tool_results),
    }


def _run_openai(api_key: str, messages_in: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import openai  # noqa: PLC0415
    except ImportError:
        return {"response": "openai package not installed.", "tool_used": None, "tool_result": None}

    client = openai.OpenAI(api_key=api_key)
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}] + list(messages_in)
    all_tool_results: list[dict[str, Any]] = []
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
                "tool_result": _merge_tool_results(all_tool_results),
            }

        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = _run_tool(tc.function.name, args)
            if tc.function.name != "geocode":
                last_tool_name = tc.function.name
                all_tool_results.append(result)
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
        "tool_result": _merge_tool_results(all_tool_results),
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
