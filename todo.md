# Open Supply Chain — Status & Next Steps

## What's built (as of 2025-05-24)

### Infrastructure
- FastAPI backend with PostGIS (Docker Compose)
- `geo_entities` table: ports, facilities, routes, locations (weather stations + stream gauges)
- `risk_events` table: NWS weather alerts + USGS earthquakes
- `risk_impacts` table: spatial join edges between risk events and affected entities
- `sources` table: provenance for every ingested dataset

### Pipelines (all runnable via `python -m pipelines.<name>` or admin API)
- `pipelines/osm.py` — OSM tri-state supply chain (ports, facilities, routes with subtypes: highway/rail/waterway/ferry)
- `pipelines/noaa.py` — NOAA CDO weather stations + NWS active alerts
- `pipelines/usgs_quakes.py` — USGS earthquake catalog (NY/NJ/CT bounding box, risk_events)
- `pipelines/usgs_water.py` — USGS NWIS active stream/estuary/lake gauges (742 sites)
- `pipelines/impact_network.py` — Rebuilds risk_impacts edge table from spatial joins

### API endpoints
- `GET /geo/entities?entity_type=&subtype=&limit=` — all geo entities
- `GET /geo/sources` — data provenance with last ingestion time
- `GET /geo/summary` — entity counts by type
- `GET /risk/events` — active NWS alerts + earthquakes
- `GET /risk/scores` — weighted risk score per entity (Σ severity_weight × confidence)
- `GET /risk/events/{id}/impacts` — entities spatially linked to a specific alert
- `POST /tools/chat` — agentic chat (Anthropic claude-haiku or OpenAI gpt-4o-mini)
- `POST /admin/ingest/*` — fire-and-forget pipeline triggers (noaa-alerts, noaa-stations, usgs-quakes, usgs-water, impact-network)

### Tools available in chat
- `geocode` — Nominatim place name → lat/lon
- `ports_near`, `facilities_near`, `routes_near` — radius search
- `weather_stations_near`, `stream_gauges_near` — NOAA/USGS monitoring sites
- `entities_in_bbox` — bounding box query
- `search_entities` — full-text name search

### Frontend (DeckGL + React)
- OSM base tiles
- Layer toggles: Routes, Facilities, Ports, Active Alerts, Risk Scores, Weather Stations, Stream Gauges
- Chat panel with tool-use and map rendering of results (gold highlight layer)
- Tooltip on hover for all entity types
- Click an alert → loads impact network edges (linked assets) as yellow highlight

---

## Open design questions / things that felt unclear

### 1. Weather stations & stream gauges — how are they actually used?
Right now they're toggleable point layers, but there's no read of their actual data (readings, flow levels, etc.). They're location markers, not live sensors. Options:
- Keep as-is (context markers — "is there a gauge near this port?")
- Add USGS instantaneous values API to fetch current readings and show in tooltip
- Use in risk scoring: if a gauge reports flood stage, flag nearby ports/facilities

### 2. Risk scores — what does the number mean visually?
Color goes green→yellow→orange→red but the threshold (score ≥ 6 = red) isn't explained anywhere in the UI. Users can't tell why something is red. Next steps:
- Add a small legend to the panel (below the Risk Scores toggle)
- Show the alert names that contributed to a score in the tooltip
- Consider making risk scores auto-on when alerts exist (don't hide behind toggle)

### 3. Impact network / linked assets is buried
Clicking an alert shows "N linked assets" in a small section and highlights them yellow, but it's easy to miss. Ideas:
- Show a popup/drawer when you click an alert (entity name, risk score, distance)
- Add count badge to the alert card when an event is selected
- Make the impact highlight more prominent (pulsing? outline?)
- Consider a sidebar panel that lists the top N impacted assets

### 4. Stations as toggles vs "native"
Weather stations and stream gauges as separate toggles feel a bit widget-y. Alternative:
- Merge into a single "Monitoring" toggle with a combined icon
- Or remove as toggles and only surface them through chat ("gauges near Newark")
- Or keep toggles but add live reading data to make them feel worth turning on

---

## Next priorities (in rough order)

### Near term
- [ ] **Impact network UX** — clickable alert → slide-in panel listing top impacted assets with name, type, distance, risk score. Much more discoverable than the buried yellow dots.
- [ ] **Risk score legend** — small color-coded legend under the Risk Scores toggle so the green/red scale is self-explanatory
- [ ] **End-to-end supply chain chains** — the data right now is nodes and edges (ports, facilities, routes) but we don't have actual cargo flow / shipment paths. Need a concept of "chain": origin → facility → port → vessel → destination
- [ ] **More data sources** (see links below) — EIA energy/fuel data, EPA sites, GDACS global disasters, USASpending for contract visibility, OpenCorporates for company linkage

### Medium term
- [ ] **MCP server** — expose tools as an MCP endpoint so external agents (Claude Desktop, other LLMs) can query the supply chain knowledge graph natively. `gofastmcp.com` is the right lib.
- [ ] **Live sensor data** — USGS instantaneous values (`waterservices.usgs.gov/nwis/iv/`) to pull current gage height and flow for stream gauges; surface in tooltip and use in risk scoring
- [ ] **Vessel tracking** — AIS data (MarineTraffic, or free NOAA AIS feeds) to overlay live vessel positions near ports
- [ ] **FAA/DOT data** — transportation.gov API for freight movement, port call data

### Longer term
- [ ] **Chain tracing** — given a disruption event, trace forward through the supply chain graph to estimate downstream impact (which facilities depend on this route? which ports serve those facilities?)
- [ ] **Scheduled ingestion** — cron or Celery to auto-refresh NOAA alerts (every 15 min), USGS quakes (hourly), impact network rebuild
- [ ] **Auth / multi-user** — right now there's no auth layer, fine for solo dev
- [ ] **Export** — let users export the current map view as GeoJSON or a report

---

## Data source links (for next ingestion work)
- GDACS global disasters: https://www.gdacs.org/gdacsapi/swagger/index.html
- EIA energy: https://www.eia.gov/opendata/
- EPA: https://www.epa.gov/data/application-programming-interface-api
- USASpending: https://api.usaspending.gov
- OpenCorporates: https://api.opencorporates.com
- ImportYeti: https://www.importyeti.com/yeti-api
- Kpler maritime: https://developers.kpler.com
- NASA EarthData: https://www.earthdata.nasa.gov
- NOAA CDO: https://www.ncdc.noaa.gov/cdo-web/webservices/v2
- DOT: https://www.transportation.gov/developer
- FastMCP: https://gofastmcp.com/getting-started/welcome
- UN Comtrade: https://comtradedeveloper.un.org
- World Bank Data360: https://data360.worldbank.org/en/api
- FRED economics: https://fred.stlouisfed.org/docs/api/fred/
- Global Forest Watch: https://data-api.globalforestwatch.org
- Climate Trace: https://api.climatetrace.org/v7/docs/index.html
- SAM.gov: https://sam.gov
