# Impact Network

The impact network turns map overlays into stored supply-chain intelligence.
Risk events are linked to physical assets with deterministic PostGIS rules, and
those links are reused by the API, tools, UI, and later MCP layer.

## Current Tool And Endpoint Surface

Already implemented before the impact network:

| Capability | Endpoint/tool | Status |
|---|---|---|
| List canonical entities | `GET /geo/entities` | implemented |
| Summarize entity counts | `GET /geo/summary` | implemented |
| List active risk events | `GET /risk/events` | implemented |
| Summarize risk events | `GET /risk/summary` | implemented |
| Search assets | `GET /tools/search` | implemented |
| Nearby ports/facilities/routes/stations | `/tools/*-near` | implemented |
| Bounding-box assets | `GET /tools/entities-in-bbox` | implemented |

Impact-network additions:

| Proposed capability | Endpoint/tool | Status |
|---|---|---|
| Store `risk_event IMPACTS asset` edges | `risk_impacts` table | implemented |
| Build persisted edges | `python -m pipelines.impact_network` | implemented |
| Alert -> impacted assets | `GET /risk/events/{event_id}/impacts` | implemented |
| Impact counts | `GET /risk/impacts/summary` | implemented |
| `get_assets_impacted_by_event(event_id)` | `GET /tools/assets-impacted-by-event` | implemented |
| `get_risk_events_near_asset(entity_id)` | `GET /tools/risk-events-near-asset` | implemented |
| `get_routes_impacted_by_alert(alert_id)` | `GET /tools/routes-impacted-by-alert` | implemented |
| `summarize_asset_exposure(entity_id)` | `GET /tools/summarize-asset-exposure` | implemented |
| Click alert -> highlight affected assets | deck.gl impact highlight layer | implemented |

## Current Rule

The first rule intentionally stays simple and explainable:

```text
risk_events.geometry intersects geo_entities.geometry
OR
risk_events.geometry is within the configured near-distance of geo_entities.geometry
```

The pipeline uses an indexed bounding-box prefilter before precise spatial
checks so the rule can scale beyond the initial NY/NJ/CT AOI.

Stored edge fields:

- `risk_event_id`
- `impacted_entity_id`
- `relationship_type = IMPACTS`
- `impact_method`: `intersects` or `near`
- `distance_m`
- `confidence`
- `evidence`

## Current Live Result

After building against the current NOAA/NWS alerts and OSM entities:

```text
140 persisted risk impact edges
92 port intersects
48 port near
```

## Data Coverage Maturity

The current active coastal alerts only impact port-like assets in the loaded
data. This is expected, not a failed relationship rule:

- Ports cover a wider coastal extent across the current OSM pulls.
- Facilities and routes are currently concentrated around the tighter
  Port Newark/New Jersey extract bbox.
- NOAA/NWS coastal alert polygons are ocean/coast focused, so they naturally
  intersect marina, ferry terminal, harbor, and port-like assets first.

To mature this layer, widen coverage in two directions:

1. Load larger OSM extracts for routes and facilities across NY, NJ, and CT.
2. Add inland risk sources such as USGS earthquakes and hazards, which should
   exercise facility and route impacts more naturally.

Until then, port-heavy impact results should be read as a data coverage signal,
not as proof that routes/facilities are unaffected in the real world.

## Next

1. Verify alert-click highlighting in browser with live PostGIS.
2. Add USGS disaster events into `risk_events`.
3. Re-run `python -m pipelines.impact_network` after each risk/entity ingestion.
4. Wrap the governed `/tools/*` functions for MCP/AI orchestration.
