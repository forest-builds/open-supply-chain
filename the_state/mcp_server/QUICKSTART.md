# The State MCP Server — Quickstart

Connect any MCP-capable agent to The State's deterministic LocationState,
brief, and watchlist surfaces in five minutes.

## 1. Run the API

The MCP server is a thin protocol shell over the HTTP API — the API must be
reachable.

```bash
docker compose up -d postgres api
# API now on http://localhost:8000
```

## 2. Run the MCP server

```bash
uv sync --all-packages
uv run the-state-mcp           # stdio transport (default)
```

HTTP transport (for containers / remote agents):

```bash
THE_STATE_MCP_TRANSPORT=streamable-http uv run the-state-mcp
# listens on http://0.0.0.0:8765/mcp
```

Or via Docker Compose (HTTP transport, wired to the `api` service):

```bash
docker compose up -d mcp_server
```

### Configuration (env)

| Variable | Default | Purpose |
|----------|---------|---------|
| `THE_STATE_API_URL` | `http://localhost:8000` | Backing API base URL |
| `THE_STATE_MCP_TRANSPORT` | `stdio` | `stdio` \| `sse` \| `streamable-http` |
| `THE_STATE_MCP_HOST` | `0.0.0.0` | Bind host (HTTP transports) |
| `THE_STATE_MCP_PORT` | `8765` | Bind port (HTTP transports) |
| `THE_STATE_MCP_LOG_LEVEL` | `INFO` | Structured log level |

## 3. Register with an agent

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "the-state": {
      "command": "uv",
      "args": ["run", "the-state-mcp"],
      "env": { "THE_STATE_API_URL": "http://localhost:8000" }
    }
  }
}
```

### Cursor

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "the-state": {
      "command": "uv",
      "args": ["run", "the-state-mcp"],
      "env": { "THE_STATE_API_URL": "http://localhost:8000" }
    }
  }
}
```

### Open-source frameworks (HTTP transport)

Point any MCP client at `http://<host>:8765/mcp` (streamable-http). Most
runtimes (LangGraph, the MCP Python/TypeScript SDKs, etc.) accept a
streamable-http URL directly.

## 4. Tool reference

| Tool | Arguments | Returns |
|------|-----------|---------|
| `get_current_state` | `place: str`, `time_window: str = "24h"` | Full `LocationState` JSON |
| `generate_operational_brief` | one of `watchlist_id` / `watched_entity_id` / `evaluation_result_id` | Brief JSON incl. permanent `url` |
| `watch_entity` | `name`, `place`, `time_window="24h"`, `thresholds?`, `delivery?` | Created watchlist JSON |
| `health_check` | — | `{"status": "ok" \| "unhealthy", ...}` |

Errors are never raised to the agent: tools return a structured
`{"error": ..., "detail": ...}` (`upstream_error`, `api_unreachable`, or
`internal_error`) so the agent can reason about failures.

All scoring is deterministic and happens server-side — the MCP server never
computes a state itself.
