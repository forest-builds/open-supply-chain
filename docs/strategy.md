# Open Supply Chain — Strategy

> Open supply-chain intelligence infrastructure for mapping how goods, risks, organizations, and routes interact.

Not an AI chatbot with a map. A verified supply-chain spatial intelligence system that AI can operate.

---

## Why This Space, Why Now

Three things are converging:

1. LLM orchestration — AI is now steerable and callable
2. Cheap geospatial infra — PostGIS, Deck.gl, open tile servers
3. Real-time open data — NOAA, OSM, USAspending, SAM.gov, Comtrade

Historically GIS software was clunky, enterprise-only, analyst-driven, and hard to query naturally. That is changing. "Show me critical infrastructure at wildfire risk" is now possible. That is a massive interface shift.

The edge here: a background in emergency management, operational systems, maps, decision support, event timelines, multi-source ingestion, and human coordination. This is closer to EOC systems and operational intelligence than generic AI SaaS. That framing matters.

---

## Why Geospatial Is Different

Location is not metadata. Location is structure.

Traditional AI systems operate on: text, tables, documents, APIs, workflows.

GIS systems operate on: coordinates, topology, adjacency, movement, containment, distance, time-space relationships.

A hurricane alert means nothing abstractly. "Hurricane intersects 38% of inbound Gulf fertilizer routes into Texas" is spatial intelligence.

Traditional AI agent:
```
Input: "Summarize this supply chain report."
LLM → retrieval → summarize → output text
```

GIS AI agent:
```
Input: "What happens if flooding closes Savannah port?"
1. Resolve location
2. Pull geospatial layers
3. Find affected routes
4. Calculate proximity / intersections
5. Analyze downstream dependencies
6. Estimate rerouting
7. Generate visual overlays
8. Explain uncertainty
```

GIS agents reason in six modes that LLMs do not naturally handle:

| Mode | Example question |
|---|---|
| Distance | Which facilities are within 50 miles? |
| Intersection | Which routes cross flood zones? |
| Movement | How do goods flow through this network? |
| Containment | Which suppliers are inside evacuation areas? |
| Network topology | What downstream nodes depend on this port? |
| Temporal-spatial state | What changed in the last 24 hours? |

Maps compress complexity visually. Humans instantly understand clusters, chokepoints, congestion, spread, corridors. That is why military, FEMA, logistics, utilities, intelligence agencies, and climate science all converge on maps. The map is the output. The intelligence is underneath it.

---

## The Architecture

```
Data Sources (OSM, NOAA, USAspending, Comtrade, AIS...)
        ↓
Ingestion Pipelines
(fetch → raw store → clean → normalize → link → embed → expose)
        ↓
Postgres / PostGIS / pgvector
        ↓  (later: Neo4j for multi-hop graph)
Deterministic Spatial Tools
        ↓
MCP Tool Layer
        ↓
AI Orchestration
        ↓
Layered Map Frontend + Explanation Panel
```

**Postgres** — relational truth: sources, raw ingestions, entities, events, decisions, confidence scores

**PostGIS** — spatial queries: within, near, intersects, contains, distance, route exposure

**pgvector** — semantic search over documents, events, entities

**JSONB** — messy source-specific metadata, preserved without schema pressure

**Neo4j** (later, not now) — add only when multi-hop graph queries become painful in SQL: supplier tracing, dependency chains, impact propagation, "show all affected downstream nodes"

Use Postgres first. Model graph-like behavior in two layers:

```text
entity_relationships: geo/entity topology such as route CONNECTS port
risk_impacts: risk_event IMPACTS geo_entity with method, distance, confidence, evidence
```

That gives graph behavior without prematurely adding another database.

---

## Canonical Data Model

Start here. Not with datasets.

**Core entities:**

```
Product        Supplier       Facility       Port
Route          Carrier        Shipment/Flow  Location
Risk Event     Contract/Award Commodity      Organization
Alert          Decision
```

**Core relationships:**

```
Supplier      PRODUCES    Product
Facility      LOCATED_IN  Location
Route         CONNECTS    Location → Location
Port          SERVES      Route
RiskEvent     IMPACTS     Location / Route / Supplier
Contract      AWARDED_TO  Organization
Organization  SUPPLIES    Product
Decision      USES        Evidence
```

This is the schema that everything else maps into. Every pipeline normalizes to these entities. Every tool queries them. Every map layer renders them.

---

## Deterministic Tool Library

The AI should not "figure out the map." The AI calls precise tools that return structured layers.

**Bad:** retrieve document chunks about flooding

**Good:** `intersect_weather_polygon(route_id, event_id)`

Spatial intelligence is computational, not semantic.

**Core tools:**

```python
get_ports_near(location, radius)
get_routes_between(origin, destination, mode)
intersect_route_with_weather(route_id)
find_facilities_in_polygon(polygon)
trace_supplier_network(product, destination)
score_disruption_exposure(route_id, event_id)
get_contracts_by_supplier(org_id)
generate_map_layer(entity_type, filters)
calculate_disruption_radius(event_id)
rank_alternate_ports(blocked_port_id)
resolve_supplier_identity(name, location)
trace_downstream_dependency(entity_id)
get_risk_events_near_location(location, radius)
get_routes_impacted_by_event(event_id)
get_supplier_exposure(org_id)
generate_disruption_scenario(product, destination, event)
```

Each tool returns a structured, evidence-locked response:

```json
{
  "layer_type": "routes",
  "features": [...],
  "confidence": 0.82,
  "source_ids": ["NOAA", "OSM", "USAspending"],
  "explanation": "Route intersects active weather alert polygon."
}
```

MCP rule: never expose raw table access. Every tool is governed, typed, and auditable. The GenAI layer calls tools, not `SELECT * FROM random_table`.

Tools currently live in `/api/tools.py` and are exposed as governed FastAPI endpoints. MCP wrappers are the next interface layer, not a replacement for those deterministic tools.

---

## Data Ingestion Strategy

One source at a time. Order matters — foundation first.

| # | Source | Entities | Status |
|---|---|---|---|
| 1 | OpenStreetMap | ports, facilities, routes | ✓ done |
| 2 | NOAA CDO | weather stations, locations | ✓ done |
| 3 | NOAA alerts / NWS | risk events | ✓ done |
| 4 | Derived impact network | risk event → impacted asset edges | ✓ done |
| 5 | USGS | risk events (earthquakes, disasters) | next |
| 6 | USAspending | contracts, procurement awards | |
| 7 | SAM.gov | organizations, suppliers | |
| 8 | UN Comtrade | trade flows, commodities | |
| 9 | AIS / maritime | shipments, routes, carriers | |
| 10 | Commodity / energy | FRED, EIA, NASDAQ Data Link | |
| 11 | Satellite / climate | NASA Earthdata, Climate TRACE | |

Each ingestion follows: `fetch → raw store → clean → normalize → link → embed → expose`

**Never throw away raw data. Store it.**

Every source gets a data contract at `sources/<name>/source_contract.yml`:

```yaml
source_name:
api_url:
auth_required:
refresh_rate:
raw_schema:
canonical_entities_created:
cleaning_rules:
join_keys:
geo_fields:
confidence_score:
license:
attribution:
```

This keeps the system from becoming a junk drawer.

---

## GenAI Pipeline

User: "Show me the supply chain risk for coffee into NYC if storms hit the Gulf."

```
1.  Parse intent
2.  Identify product = coffee, destination = NYC
3.  Infer likely origins / routes
4.  Call trace_supplier_network(coffee, NYC)
5.  Call intersect_route_with_weather(route_ids, storm_polygon)
6.  Call score_disruption_exposure(route_id, event_id)
7.  Call rank_alternate_ports(blocked_port_id)
8.  Generate map layers with confidence + source attribution
9.  Generate narrative explanation
10. Save decision + evidence to database
```

Every step is auditable. Every output links back to a source. The system can explain why it drew what it drew.

---

## The Learning Loop

The system improves by storing what happens after each query:

- queries issued
- entities selected
- map layers generated
- decisions produced
- user feedback
- confirmed / rejected entity links
- new relationships discovered

The database learns through better entity resolution, embeddings, confidence scores, scenario templates, and decision outcomes. Not "the model learns magically." The data quality compounds.

---

## The Moat

The map is the interface. The moat is everything underneath it.

**What not to rely on — all of these are copyable:**
- Nice UI
- Chat interface
- Prompt quality
- Generic map visualization
- Which LLM you're using
- Basic ingestion scripts

**What builds real defensibility:**

**1. Cleaned, provenance-tagged data layer**
Anyone can fetch NOAA, OSM, USAspending, SAM.gov. Fewer people build entity resolution, source confidence tracking, historical snapshots, route normalization, supplier/location matching, and disruption-event history. That becomes a proprietary asset.

**2. Deterministic tool library**
LLMs can imitate an answer. They cannot reliably recreate tested geospatial computations without the same tools and data. The tool library is the product.

**3. Evaluation benchmarks**
Build a benchmark set: 100 disruption scenarios with expected affected nodes, alternate routes, ground-truth references, accuracy scores, latency scores, confidence calibration. You can prove the system works. That is defensible.

**4. Workflow lock-in**
The value compounds inside the customer's workflow: saved scenarios, custom supplier lists, private facilities, internal routes, risk preferences, decision history, team alerts, recurring reports. Once a user has their operating picture in the system, switching costs rise.

**5. Distribution wedge**
"Open-data supply-chain resilience intelligence for governments, emergency managers, and mid-market operators." Not competing with SAP head-on. The angle matters.

**6. Trust and provenance**
Every map layer must answer: Where did this come from? When was it updated? Is this observed or inferred? What confidence? What tool generated it? A generic LLM answer cannot compete with a verifiable operational record.

---

## MVP Wedge

Build this first:

A map-first supply chain disruption intelligence tool where a user enters a product, destination, and scenario — and the system generates an explainable supply chain risk map using open data.

**Input:**
- Product: Coffee
- Destination: New York City
- Scenario: Hurricane impacting Gulf shipping

**Output:**
- Map with affected nodes, ports, routes
- Weather / disaster overlay
- Risk score with confidence
- Alternative routes ranked
- Narrative explanation with source attribution

Discipline: one source, one canonical entity, one useful scenario. Then expand.

---

## Repo Structure

```
/sources
  osm/            source_contract.yml, extract_manifest.yml, overpass_queries.py, raw/
  noaa/           source_contract.yml, alerts_contract.yml, raw/
/db
  schema.sql
/pipelines
  osm.py
  osm_extracts.py
  noaa.py
  impact_network.py
/api
  main.py
  routes.py
  tools.py          ← deterministic spatial tools exposed as FastAPI endpoints
  chat.py           ← LLM orchestration over governed tools
  admin.py          ← ingestion/rebuild triggers
/app
  map_ui/
/docs
  strategy.md
  pipeline_status.md
  impact_network.md
  canonical_model.md
  source_registry.md
```

---

## Source Registry

**Geospatial Foundation**
- OpenStreetMap — ports, facilities, routes, infrastructure
- NOAA CDO — weather stations
- NOAA NWS — active alerts, storm tracks
- NASA Earthdata — satellite imagery, environmental monitoring
- USGS — earthquake and disaster hazards

**Maritime / Shipping**
- MarineTraffic / AISHub — vessel tracking, port congestion
- Port of Los Angeles Data Portal — throughput, containers
- UNCTAD Maritime Transport — global shipping statistics
- Baltic Exchange — Baltic Dry Index, freight benchmarks

**Trade / Customs**
- UN Comtrade — international trade flows
- USA Trade Online — U.S. import/export
- World Bank Open Data — economic indicators
- OECD Trade Data — supply chain economics

**Transportation / Infrastructure**
- Bureau of Transportation Statistics — U.S. freight
- Federal Highway Administration — trucking corridors
- FAA Data Portal — aviation cargo

**Procurement / Suppliers**
- USAspending — federal contracts and flows
- SAM.gov — vendor registrations
- OpenCorporates — corporate entity relationships
- ImportYeti — supplier/manufacturer shipment relationships

**Commodity / Financial**
- FRED — inflation, commodities, macro indicators
- NASDAQ Data Link — commodity datasets
- EIA — oil, gas, energy logistics

**Sustainability / ESG**
- Climate TRACE — emissions tracking
- Global Forest Watch — deforestation, land use
- EPA — pollution and environmental risk
