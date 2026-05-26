# open-supply-chain

[![Live Map](https://img.shields.io/badge/live%20map-GitHub%20Pages-blue?logo=github)](https://forest-builds.github.io/open-supply-chain/)


Open supply-chain intelligence infrastructure for mapping how goods, risks,
organizations, facilities, ports, and routes interact.

The current vertical slice uses:

- OpenStreetMap for base supply-chain geography: ports, facilities, routes
- NOAA CDO for optional weather station observation context
- NOAA/NWS active alerts for risk events
- GDACS for global disaster events (hurricanes, floods, volcanoes, earthquakes)
- EPA Envirofacts TRI for active industrial/chemical facility locations
- EIA Open Data for power plant and energy facility locations
- USASpending.gov for federal logistics/freight contractor locations
- AISHub for live vessel position tracking near ports
- USGS for earthquake events and stream/water gauge monitoring sites
- A persisted `risk_impacts` edge table for event-to-asset exposure
- Postgres + PostGIS as the system of record
- FastAPI for canonical GeoJSON, tools, chat, and admin endpoints
- Claude Sonnet with multi-hop tool chaining for AI-assisted risk reasoning
- deck.gl for the map-first UI

## Project Shape

```text
/sources
  /osm                 OpenStreetMap contracts, AOI, queries, extract manifest
  /noaa                NOAA contracts and raw payloads
  /gdacs               GDACS global disaster event contract
  /epa                 EPA Envirofacts TRI facility contract
  /eia                 EIA energy facility contract
  /usaspending         USASpending federal contractor contract
  /ais                 AISHub vessel feed contract
/db
  schema.sql           PostGIS schema
/pipelines
  osm.py               Overpass probe ingestion
  osm_extracts.py      Geofabrik extract ingestion
  noaa.py              NOAA stations and NWS alert ingestion
  gdacs.py             GDACS global disaster events → risk_events
  epa.py               EPA TRI industrial facilities → geo_entities
  eia.py               EIA power plants → geo_entities
  usaspending.py       Federal logistics contractors → geo_entities
  ais.py               Live vessel positions → geo_entities
  impact_network.py    Build persisted risk_impacts edges
/api
  main.py              FastAPI app
  routes.py            GeoJSON/risk/source endpoints
  tools.py             Deterministic spatial tools (22 tools)
  chat.py              Claude Sonnet multi-hop reasoning endpoint
  mcp_server.py        FastMCP server over governed tools
  admin.py             Background ingestion triggers
/app
  /map_ui              deck.gl + Vite app
/docs
  strategy.md
  pipeline_status.md
  impact_network.md
  data_contracts.md
  canonical_model.md
  source_registry.md
```

## First AOI

The first area of interest is the NY/NJ/CT region, stored at:

```text
sources/osm/tri_state_aoi.geojson
```

The canonical OSM extract path now covers Connecticut, New Jersey, and New York
statewide through Geofabrik extracts. Overpass jobs are still useful as small
probes, but the repeatable path is the extract downloader/loader.

## Setup

Copy environment defaults:

```bash
cp .env.example .env
```

Start PostGIS:

```bash
docker compose up -d postgres
```

Install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Load OSM data. Use Overpass for small probes:

```bash
python -m pipelines.osm --job nyc_harbor_ports
python -m pipelines.osm --job nyc_harbor_facilities
python -m pipelines.osm --job nyc_harbor_routes
```

Prefer Geofabrik extracts for repeatable scalable ingestion:

```bash
python -m pipelines.osm_extracts list
python -m pipelines.osm_extracts download \
  --region connecticut \
  --region new_jersey \
  --region new_york
python -m pipelines.osm_extracts load \
  --region connecticut \
  --region new_jersey \
  --region new_york \
  --layer port \
  --layer facility \
  --layer route
```

Load NOAA observation and risk context:

```bash
python -m pipelines.noaa --dataset stations
python -m pipelines.noaa --dataset alerts
```

Load additional data sources (no API key required):

```bash
python -m pipelines.gdacs          # GDACS global disasters → risk_events
python -m pipelines.epa            # EPA TRI industrial facilities → geo_entities
python -m pipelines.usaspending    # Federal freight contractors → geo_entities
```

Load API-key-gated sources (gracefully skip if key is missing):

```bash
EIA_API_KEY=your-key python -m pipelines.eia     # EIA power plants
AIS_API_KEY=your-key python -m pipelines.ais     # Live vessel positions
```

Rebuild the impact network after any new data load:

```bash
python -m pipelines.impact_network
```

For no-database smoke tests, use `--dry-run` on any pipeline command.

Start the API:

```bash
uvicorn api.main:app --reload
```

Run the MCP server locally:

```bash
fastmcp run fastmcp.json
```

The MCP server exposes governed spatial search tools plus GIS-native metadata
and topology helpers: CRS/layer metadata, entity relation checks, and bounded
entity buffers. All geometry is returned as GeoJSON in EPSG:4326 longitude /
latitude order.

Verify and inspect the MCP registration:

```bash
fastmcp inspect fastmcp.json
fastmcp dev inspector fastmcp.json
```

Register it with Claude Desktop:

```bash
fastmcp install claude-desktop api/mcp_server.py:mcp \
  --name "Open Supply Chain" \
  --with fastmcp==3.3.1 \
  --with-editable .
```

For another MCP-compatible client, generate standard MCP JSON:

```bash
fastmcp install mcp-json api/mcp_server.py:mcp \
  --name "Open Supply Chain" \
  --with fastmcp==3.3.1 \
  --with-editable .
```

Start the map UI:

```bash
cd app/map_ui
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Run tests and coverage. Python coverage is gated at 90%:

```bash
pytest
cd app/map_ui
npm test -- --run
npm run build
```

## API Endpoints

```text
GET /health
GET /geo/summary
GET /geo/entities
GET /geo/entities?entity_type=port
GET /geo/entities?entity_type=facility
GET /geo/entities?entity_type=route
GET /geo/sources
GET /aoi/ny_nj_ct
GET /risk/events
GET /risk/summary
GET /risk/events/{event_id}/impacts
GET /risk/impacts/summary
GET /risk/scores
GET /chains/examples/refrigerated-food-port-newark
GET /tools/catalog
GET /tools/search
GET /tools/ports-near
GET /tools/facilities-near
GET /tools/routes-near
GET /tools/stream-gauges-near
GET /tools/weather-stations-near
GET /tools/entities-in-bbox
GET /tools/assets-impacted-by-event
GET /tools/risk-events-near-asset
GET /tools/routes-impacted-by-alert
GET /tools/summarize-asset-exposure
GET /tools/topology-relations-for-entity
GET /tools/buffer-entity
GET /tools/layer-metadata
GET /tools/gis-metadata
POST /tools/chat
POST /admin/ingest/noaa-alerts
POST /admin/ingest/noaa-stations
POST /admin/ingest/impact-network
POST /admin/ingest/gdacs
POST /admin/ingest/epa
POST /admin/ingest/eia
POST /admin/ingest/usaspending
POST /admin/ingest/ais
```

## Scalability Rules

- Every source gets a source contract.
- Raw payloads are always preserved in `raw_ingestions`.
- Source-specific fields live in `JSONB`.
- Canonical entities stay stable and source-agnostic.
- The UI and MCP tools consume governed API endpoints, not raw source tables.
- Add new sources by extending `/sources`, `/pipelines`, and canonical tables;
  do not hard-code source assumptions into the deck.gl app.

See [docs/pipeline_status.md](docs/pipeline_status.md) for the current pipeline
shape and coverage status.

## AI Reasoning

The `/tools/chat` endpoint uses Claude Sonnet with multi-hop tool chaining.
The model receives actual entity names, IDs, distances, severity levels, and
event headlines from each tool call — enabling it to chain:

```
geocode → search_entities → risk_events_near_asset → summarize_asset_exposure
```

or:

```
geocode → risk_events_near → assets_impacted_by_event
```

Six risk-reasoning tools are exposed to the model: `search_entities`,
`risk_events_near_asset`, `risk_events_near`, `assets_impacted_by_event`,
`summarize_asset_exposure`, and `trace_supply_chain`. Results from all tool
rounds are merged into a single FeatureCollection for the map overlay.

## Data Coverage Notes

The current asset layer covers NY/NJ/CT statewide:
- **Ports and routes** — OSM Geofabrik extracts
- **Industrial facilities** — ~3,700 active EPA TRI sites
- **Energy facilities** — EIA power plants and generators
- **Freight contractors** — USASpending.gov logistics/freight NAICS awardees
- **Vessels** — AISHub live AIS positions (requires API key)

Risk events come from NOAA/NWS active alerts, USGS earthquake reports, and
GDACS global disaster events. The `risk_impacts` edge table is rebuilt after
each ingestion run and links events spatially to affected supply chain assets.

Attribution: map and source data from OpenStreetMap contributors.
