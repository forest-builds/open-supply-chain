# open-supply-chain

[![Live Map](https://img.shields.io/badge/live%20map-GitHub%20Pages-blue?logo=github)](https://forest-builds.github.io/open-supply-chain/)


Open supply-chain intelligence infrastructure for mapping how goods, risks,
organizations, facilities, ports, and routes interact.

The current vertical slice uses:

- OpenStreetMap for base supply-chain geography: ports, facilities, routes
- NOAA CDO for optional weather station observation context
- NOAA/NWS active alerts for risk events
- A persisted `risk_impacts` edge table for alert-to-asset exposure
- Postgres + PostGIS as the system of record
- FastAPI for canonical GeoJSON, tools, chat, and admin endpoints
- deck.gl for the map-first UI

## Project Shape

```text
/sources
  /osm                 OpenStreetMap contracts, AOI, queries, extract manifest
  /noaa                NOAA contracts and raw payloads
/db
  schema.sql           PostGIS schema
/pipelines
  osm.py               Overpass probe ingestion
  osm_extracts.py      Geofabrik extract ingestion
  noaa.py              NOAA stations and NWS alert ingestion
  impact_network.py    Build persisted risk_impacts edges
/api
  main.py              FastAPI app
  routes.py            GeoJSON/risk/source endpoints
  tools.py             Deterministic spatial tools
  chat.py              LLM-backed tool orchestration endpoint
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

The initial Overpass and extract loads use tighter NYC metro/Newark/Long Island
Sound bboxes so local pulls stay practical. The canonical AOI and database shape
are ready to widen as OSM extract coverage expands across NY, NJ, and CT.

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
python -m pipelines.osm_extracts download --region new_jersey
python -m pipelines.osm_extracts load \
  --region new_jersey \
  --layer port \
  --layer facility \
  --layer route \
  --bbox 40.65,-74.20,40.72,-74.12
```

Load NOAA observation and risk context:

```bash
python -m pipelines.noaa --dataset stations
python -m pipelines.noaa --dataset alerts
python -m pipelines.impact_network
```

For no-database smoke tests, use `--dry-run` on OSM/NOAA pipeline commands.

Start the API:

```bash
uvicorn api.main:app --reload
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
GET /tools/catalog
GET /tools/search
GET /tools/assets-impacted-by-event
GET /tools/risk-events-near-asset
GET /tools/routes-impacted-by-alert
GET /tools/summarize-asset-exposure
POST /tools/chat
POST /admin/ingest/noaa-alerts
POST /admin/ingest/noaa-stations
POST /admin/ingest/impact-network
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

## Data Coverage Notes

The current loaded data is intentionally still uneven. Ports cover a wider
coastal extent than routes and facilities, while routes/facilities are currently
concentrated around the tighter Port Newark/New Jersey extract bbox. Current
NOAA/NWS coastal alerts therefore produce port-heavy impacts. This is a source
coverage signal, not proof that inland routes or facilities are unaffected.

Next coverage work: widen OSM extracts across NY/NJ/CT and add inland risk
sources such as USGS.

Attribution: map and source data from OpenStreetMap contributors.
