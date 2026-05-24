# Canonical Model

The canonical model is intentionally small at the start. Sources can be messy;
canonical entities should stay boring and stable.

## Geo Entities

`geo_entities` stores source-derived geography used by the map and scenario
engine.

Core fields:

- `entity_type`: `port`, `facility`, `route`, `location`, `aoi`
- `subtype`: optional source-derived canonical subtype, such as
  `storage_tank` or `warehouse`
- `name`
- `description`
- `geometry`
- `source_name`
- `source_entity_id`
- `source_tags`
- `confidence`

## Relationships

`entity_relationships` stores graph-like links while Postgres remains the
system of record for geo-entity topology.

Examples:

- `route CONNECTS port`
- `facility LOCATED_IN location`
- `organization SUPPLIES product`

`risk_impacts` stores event-to-asset edges derived from deterministic spatial
rules. This keeps active hazards auditable without forcing `risk_events` into the
same table shape as physical geography.

Examples:

- `risk_event IMPACTS port` by intersection
- `risk_event IMPACTS facility` within the configured near-distance threshold
- `risk_event IMPACTS route` with source event severity preserved as evidence

Current impact rule:

```text
risk_events.geometry ST_Intersects geo_entities.geometry
OR
risk_events.geometry ST_DWithin geo_entities.geometry by configured meters
```

Each edge stores `impact_method`, `distance_m`, `confidence`, and JSONB
`evidence` so UI, API tools, and later MCP calls can explain why a feature was
highlighted.

## Areas Of Interest

`areas_of_interest` stores named polygons that constrain ingestion, analysis,
and UI viewports. The first AOI is `ny_nj_ct`.
