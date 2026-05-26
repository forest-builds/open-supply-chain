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

GDACS, EPA TRI, EIA, USASpending, and AIS
  -> source-specific live APIs
  -> risk_events or geo_entities
  -> admin-triggered ingestion endpoints
  -> dry-run smoke coverage and normalized DB helpers
```

## Implemented

- NY/NJ/CT area of interest.
- Source contracts/manifests for OSM and NOAA.
- Named OSM Overpass jobs for ports, facilities, and routes.
- Manifest-driven Geofabrik extract downloader for CT/NJ/NY.
- MD5 verification for downloaded `.osm.pbf` extracts.
- Local `.osm.pbf` parser for ports, facilities, and routes.
- Statewide Geofabrik extract load for Connecticut, New Jersey, and New York.
- Raw payload preservation for external source pulls.
- Canonical `geo_entities` normalization.
- Route subtype derivation for `highway`, `rail`, `waterway`, and `ferry`.
- Facility subtype derivation for `warehouse`, `storage_tank`, `logistics`, and
  `industrial_site`.
- NOAA CDO station ingestion as optional observation context.
- NOAA/NWS active alert ingestion into `risk_events`.
- GDACS live global disaster ingestion into `risk_events`.
- EPA Envirofacts TRI ingestion into `geo_entities` as active industrial
  facilities.
- EIA Open Data v2 power plant ingestion into `geo_entities`, with graceful
  skip when `EIA_API_KEY` is missing.
- USASpending.gov logistics contractor ingestion into `geo_entities`, using
  place-of-performance geocoding with state centroid fallback.
- AISHub vessel feed ingestion into `geo_entities`, with graceful skip when
  `AIS_API_KEY` is missing.
- Persisted `risk_impacts` edges from active risk events to ports, facilities,
  and routes.
- Risk score endpoint derived from active impact edges.
- PostGIS storage and spatial indexes.
- FastAPI GeoJSON, source, risk, tool, chat, and admin endpoints.
- deck.gl map rendering with layer controls, alert impact highlighting, risk
  scores, optional stations, and chat result overlays.
- Local raw-file fallback when PostGIS is down for OSM seed data.
- AI chat upgraded to Claude Sonnet with multi-hop tool chaining: the model
  receives entity names, IDs, distances, and risk details from each tool call
  so it can chain `search_entities → risk_events_near_asset →
  summarize_asset_exposure` across multiple rounds.
- Six risk-reasoning tools exposed to the model: `search_entities`,
  `risk_events_near_asset`, `risk_events_near` (new spatial query by lat/lon),
  `assets_impacted_by_event`, `summarize_asset_exposure`, `trace_supply_chain`.
- All non-geocode tool results across rounds merged into a single
  FeatureCollection for map overlay (previously only last result was shown).

## Current Local Data

Latest integrity check (after EPA TRI + USASpending ingestion and impact rebuild):

```text
sources: 9+
geo_entities: ~140,000+
risk_events: live (varies with active alerts)
risk_impacts: 29,142+
```

Entity breakdown (approximate):

```text
facility: ~18,000+ (OSM + EPA TRI ~3,700 + EIA power plants + USASpending contractors)
location/weather_station: 1,910
location/stream_gauge: 742
location/vessel: live (AIS, requires key)
port: 1,086
route: 117,651
```

Risk/impact breakdown (approximate, varies with active alerts):

```text
facility: 2,000+ intersects, 300+ near
port: 370+ intersects, 140+ near
route: 22,000+ intersects, 3,000+ near
```

## Test Coverage

Python coverage is gated at 90% in `pyproject.toml`.

Latest local run:

```text
175 passed
Frontend: 5 Vitest interaction tests passed
Build: Vite build passed with deck.gl bundle-size warning
```

Covered:

- OSM tag classification, geometry conversion, raw payload normalization, DB
  helper calls, and CLI dispatch.
- Geofabrik extract manifest, resumable download path, checksum verification,
  parser branches, load dispatch, and status reporting.
- NOAA station and alert normalization, paged fetch behavior, zone geometry
  resolution, raw insertion helpers, DB helper calls, and CLI dispatch.
- USGS earthquake and water-gauge fetch parameterization, parsing,
  normalization, DB helper calls, dry-run behavior, and CLI dispatch.
- GDACS, EPA TRI, EIA, USASpending, and AIS source contracts, normalization,
  DB helper calls, dry-run behavior, and admin ingestion scheduling.
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

- Current OSM ports, facilities, and routes are loaded from statewide
  Connecticut, New Jersey, and New York Geofabrik extracts.
- Current NOAA/NWS alerts are coastal, so persisted impact edges are still
  shaped by the active alert feed.
- USGS water gauges are present as monitoring locations; live readings are not
  yet ingested.
- USGS earthquake ingestion has started and should be expanded into the broader
  inland disaster/hazard layer.

## Next Pipeline Steps

1. Improve UX around risk reasoning — surface severity breakdown and impact chains directly in the map UI (not just in chat).
2. Add UN Comtrade/Comtrade Plus as product-country flow context (what goods move through which corridors).
3. Add USGS hazards/flood inundation layers as extended risk events.
4. Add `ingestion_id` provenance directly on `geo_entities` for auditable lineage.
5. Schedule automated nightly ingestion for GDACS, NOAA alerts, and AIS.
