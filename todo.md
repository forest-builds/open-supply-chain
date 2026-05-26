# Open Supply Chain — Status & Next Steps

## What's built (as of 2026-05-25)

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

### Current local coverage
- OSM statewide CT/NJ/NY extract coverage: 117,651 routes, 14,460 facilities, 1,086 ports
- NOAA CDO: 1,910 weather station locations
- USGS NWIS: 742 stream/estuary/lake gauge locations
- Active risk events: 5 NOAA/NWS alerts, 1 USGS earthquake
- Persisted impact edges: 28,611 across routes, facilities, and ports

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
- [x] **Widen OSM coverage** — CT/NJ/NY statewide Geofabrik extracts loaded for ports, facilities, and routes
- [ ] **Impact network UX** — clickable alert → slide-in panel listing top impacted assets with name, type, distance, risk score. Much more discoverable than the buried yellow dots.
- [ ] **Risk score legend** — small color-coded legend under the Risk Scores toggle so the green/red scale is self-explanatory
- [x] **First concrete chain example** — refrigerated food imports through Port Newark now has `/chains/examples/refrigerated-food-port-newark` and the `example_refrigerated_food_port_newark` MCP/tool wrapper.
- [ ] **End-to-end supply chain chains** — the data right now is nodes and edges (ports, facilities, routes) but we don't have actual cargo flow / shipment paths. Need a concept of "chain": origin → facility → port → vessel → destination
- [ ] **More data sources** (see links below) — EIA energy/fuel data, EPA sites, GDACS global disasters, USASpending for contract visibility, OpenCorporates for company linkage

### Medium term
- [x] **MCP server** — expose tools as an MCP endpoint so external agents (Claude Desktop, other LLMs) can query the supply chain knowledge graph natively. `gofastmcp.com` is the right lib.
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

---

Your instinct is correct. The issue is no longer “styling.”

It’s that the system currently has multiple competing mental models at once.

Right now it is simultaneously:

* dashboard
* alert feed
* AI chat
* GIS viewer
* operational system
* metrics panel
* scenario engine

So the user doesn’t know:

“What is this thing primarily for?”

That’s why it feels messy.

You need one dominant interaction model.

And I think the answer is:

The map is primary.

The left rail is generated context.

AI orchestrates views.

That’s it.

⸻

The core problem

You are trying to expose:

* data
* controls
* alerts
* metrics
* chat
* modes

all at once.

That creates cognitive fragmentation.

Minimalism is not:

fewer elements

It is:

one clear system.

⸻

The actual cohesive model

LEFT PANEL SHOULD ONLY ANSWER 3 THINGS

1. What is happening?

Operational summary.

2. Why does it matter?

Impacts + confidence.

3. What can I ask next?

Command interface.

That’s it.

Everything else becomes generated or contextual.

⸻

What I would REMOVE immediately

Remove entirely:

* Signals metric grid
* “Additional intelligence”
* Static infrastructure counts
* Port interfaces count
* System confidence count
* Hydrologic signals count

These are database stats masquerading as product value.

Users do not care.

Those belong:

* in debug
* analytics
* secondary intel panels
* hover states
* drill-downs

Not the primary surface.

⸻

Pressure signals are wrong structurally

Correct instinct again.

They currently:

* repeat
* compete with the summary
* don’t drive interaction
* aren’t spatially anchored

Instead:
make the map itself carry the signals.

Meaning:

* highlighted corridor
* glowing impacted zone
* animated degradation
* spatial annotation

Then the panel summarizes the current operational state.

Not duplicate it.

⸻

The mode buttons should become worldview modes

Not tabs.

This is important.

LIVE

Current operational state.

FLOW

Movement + dependencies.

SCENARIO

Simulation mode.

INTEL

AI-generated observations.

MEMORY

Historical replay.

Each mode should materially change:

* layers
* animation
* summaries
* interaction

Otherwise remove them.

Right now they feel decorative because they don’t alter cognition.

⸻

The panel should probably look more like this

OPEN SUPPLY CHAIN
LIVE • Atlantic Corridor
Operational pressure increasing.
6 coastal disruption signals are impacting
freight movement across the NY/NJ corridor.
Primary impacts:
• Increased coastal route exposure
• Elevated port dwell risk
• Regional hydrologic monitoring active
Confidence: Moderate
Updated 12s ago

Then:

Ask the network...

Then the rest of the UI becomes:

* generated overlays
* contextual cards
* hover intelligence
* expandable detail

NOT permanent widgets.

⸻

Critical realization:

The UI should emerge from the query

Meaning:

User asks:

"What vulnerabilities exist in food imports to NYC?"

THEN:

* food supply layers appear
* import corridors illuminate
* relevant ports emerge
* dependency nodes expand
* operational notes appear

The UI becomes adaptive.

Not static.

That’s the AI-native shift.

⸻

Your current architecture is still:

“software with AI added”

You need:

“AI generating operational software in real time”

That is the frontier.

⸻

Another major issue:

You’re exposing ontology too early

Users should not initially see:

* infrastructure nodes
* hydrologic signals
* port interfaces
* risk edges

Those are backend concepts.

The user wants:

* operational understanding
* scenario reasoning
* consequence visibility

Expose abstractions first.
Reveal ontology later.

⸻

The actual scalable mental model

The product should feel like:

A spatial intelligence engine
that generates operational understanding
from live world data.

Not:

A GIS dashboard with AI.

That distinction matters enormously.

⸻

My recommendation

Collapse the UI dramatically.

Keep:

* title
* operational summary
* confidence/update state
* single command field
* map

Everything else:

generated dynamically.

This is the hardest transition for builders because it feels like:

“there’s not enough UI”

But AI-native systems will likely have:

* less permanent chrome
* more generated context
* more adaptive surfaces
* fewer static controls

You’re very close to discovering that organically.
