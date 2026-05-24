# Pipeline Status

Current vertical slice:

```text
OpenStreetMap
  -> Geofabrik regional extract or Overpass probe
  -> verified local source artifact or saved raw JSON
  -> raw_ingestions
  -> normalize_elements()
  -> geo_entities
  -> FastAPI GeoJSON + deterministic tools
  -> deck.gl layers

NOAA CDO stations
  -> raw_ingestions
  -> geo_entities location/weather_station
  -> optional deck.gl layer

NOAA/NWS active alerts
  -> raw_ingestions
  -> risk_events
  -> risk_impacts derived against core geo_entities
  -> FastAPI impact endpoints + deterministic tools
  -> deck.gl alert click/highlight + risk-score layer
```

## Implemented

- NY/NJ/CT area of interest.
- Source contracts/manifests for OSM and NOAA.
- Named OSM Overpass jobs for ports, facilities, and routes.
- Manifest-driven Geofabrik extract downloader for CT/NJ/NY.
- MD5 verification for downloaded `.osm.pbf` extracts.
- Local `.osm.pbf` parser for ports, facilities, and routes.
- Raw payload preservation for external source pulls.
- Canonical `geo_entities` normalization.
- Facility subtype derivation for `warehouse`, `storage_tank`, `logistics`, and
  `industrial_site`.
- NOAA CDO station ingestion as optional observation context.
- NOAA/NWS active alert ingestion into `risk_events`.
- Persisted `risk_impacts` edges from active risk events to ports, facilities,
  and routes.
- Risk score endpoint derived from active impact edges.
- PostGIS storage and spatial indexes.
- FastAPI GeoJSON, source, risk, tool, chat, and admin endpoints.
- deck.gl map rendering with layer controls, alert impact highlighting, risk
  scores, optional stations, and chat result overlays.
- Local raw-file fallback when PostGIS is down for OSM seed data.

## Current Local Data

Latest integrity check:

```text
sources: 4
raw_ingestions: 6
geo_entities: 4,080
risk_events: 5
risk_impacts: 140
entity_relationships: 0
```

Entity breakdown:

```text
facility: 288
location/weather_station: 1,910
port: 230
route: 1,652
```

Risk/impact breakdown:

```text
High Surf Advisory / Minor: 2
Rip Current Statement / Moderate: 3
risk_impacts: 92 port intersects, 48 port near
```

## Test Coverage

Python coverage is gated at 90% in `pyproject.toml`.

Latest local run:

```text
103 passed
TOTAL coverage: 92.19%
Frontend: 3 Vitest interaction tests passed
Build: Vite build passed with deck.gl bundle-size warning
```

Covered:

- OSM tag classification, geometry conversion, raw payload normalization, DB
  helper calls, and CLI dispatch.
- Geofabrik extract manifest, resumable download path, checksum verification,
  parser branches, load dispatch, and status reporting.
- NOAA station and alert normalization, paged fetch behavior, zone geometry
  resolution, raw insertion helpers, DB helper calls, and CLI dispatch.
- Impact-network source registration and bounded spatial rule.
- API fallback responses, CORS/preflight middleware, favicon route, risk events,
  risk impacts, risk scores, sources, and tools.
- Chat provider selection, geocoding, tool dispatch, provider tool loops, and
  not-configured behavior.
- Admin ingestion/rebuild trigger scheduling and failure logging.
- Frontend summary rendering, layer fetch behavior, station opt-in, and alert
  impact-edge loading.

Not covered yet:

- Full browser rendering with real WebGL.
- Full Overpass network fetch path against the public API.
- Full Geofabrik extract download of large state files.
- Full end-to-end pipeline command invocation against PostGIS and live networks.

## Data Coverage Notes

- Current ports cover a wider coastal area than routes/facilities.
- Current routes and facilities are concentrated around the tighter Port
  Newark/New Jersey extract bbox.
- Current NOAA/NWS alerts are coastal, so persisted impact edges are port-heavy.
- This is a known AOI/source maturity issue. Wider OSM extracts and inland risk
  sources such as USGS should produce more route and facility impacts.

## Next Pipeline Steps

1. Verify the impact highlight/risk-score layers in-browser with real WebGL.
2. Widen OSM extract coverage for routes and facilities across NY/NJ/CT.
3. Add USGS disasters as the next `risk_events` source.
4. Rebuild `risk_impacts` after each risk/entity ingestion.
5. Add MCP wrappers around the governed `/tools/*` surface.
6. Add `ingestion_id` provenance directly on `geo_entities`.
7. Add UN Comtrade/Comtrade Plus as product-country flow context.
