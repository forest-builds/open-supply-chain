# the-state (mounted)

This directory is the former [`the-state`](https://github.com/forest-builds/the-state)
repo, physically consolidated into open-supply-chain. It is mounted into the main
app at `/the-state` (see `api/main.py` and `mount.py`) and ships as its own
`project.scripts` entry point for the MCP server — it is **not** merged into
open-supply-chain's data model.

## What this is

- `api/` — the-state's FastAPI app (LocationState synthesis, watchlists, briefs,
  SHA-256 credentialing, x402 payment gating), unmodified internals.
- `mcp_server/` — a thin MCP client over that API (`uv run the-state-mcp`).
- `packages/` — `state_products`, `decision_apis`, `payments`, `sdk`, `state_engine`,
  `ingestion` (NYC/NOAA/OpenFEMA collectors), each a `uv` workspace member.
- `tests/` — the-state's own test suite, run separately: `uv run pytest the_state/tests/`.

## What this is NOT (yet)

- **Not sharing a database.** the-state still reads/writes its own schema
  (`THE_STATE_DATABASE_URL`, SQLAlchemy + Alembic) — a completely different
  stack from open-supply-chain's own `psycopg` + PostGIS layer. Nothing here
  touches `geo_entities` / `risk_events`.
- **Not sharing an MCP server.** the-state's MCP server is its own process
  (raw `mcp` SDK, calls the HTTP API). open-supply-chain's MCP server
  (`api/mcp_server.py`, FastMCP) is untouched. Two tool sets, two processes,
  one repo.
- **Not wired into production.** The live Fly.io deployment
  (`open-supply-chain-api`) and its Dockerfile only ever shipped `api/` and
  `sources/`. Putting the-state's routes in front of real traffic is a
  separate, explicit decision — this consolidation is code/repo-level only.

## Why it's structured this way

the-state's own code uses flat, un-namespaced imports (`from core.config import
settings`, `from routes import ...`) because it was built to run as its own
project root. Rewriting those to fit open-supply-chain's package layout would
be a much larger, riskier change than the actual goal here — reducing repo
sprawl. `mount.py` puts `the_state/api/` on `sys.path` so the existing code
runs unmodified; only the resulting FastAPI `app` object crosses into
open-supply-chain's process.

## Known rough edges

- `the_state/api`'s installed top-level module names (`core`, `models`,
  `routes`, `schemas`, `services`, `cli`) are generic enough to collide with a
  future package. No collision today; worth namespacing if this repo grows
  more members.
- Both settings classes accept a bare `DATABASE_URL` / `database_url` env var
  as a fallback alias alongside their prefixed names
  (`THE_STATE_DATABASE_URL` for the-state). Set the prefixed var explicitly in
  any shared environment to avoid ambiguity.

## Next steps, if ever wanted

A real data-model merge — the-state's NYC ingestion feeding
open-supply-chain's `risk_events`/`geo_entities` directly, `LocationState`
becoming a read-layer over the unified schema — was deliberately deferred.
Worth doing once there's a concrete case for cross-referencing (e.g. an NYC
disruption driven by a GDACS event), not before.
