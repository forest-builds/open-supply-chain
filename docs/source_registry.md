# Source Registry

| Source | Status | Purpose | Current canonical output |
| --- | --- | --- | --- |
| OpenStreetMap | active | Base geography, ports, facilities, roads, rail, waterways | `geo_entities`: `port`, `facility`, `route` |
| NOAA CDO | active | Weather station observation locations | `geo_entities`: `location/weather_station` |
| NOAA/NWS active alerts | active | Current weather and coastal hazard alerts | `risk_events` |
| Derived risk impacts | active derived source | Deterministic event-to-asset exposure edges | `risk_impacts` |
| USGS | next | Earthquake and disaster events | planned `risk_events` |
| USAspending | planned | Procurement awards and contract flow | planned contracts/organizations |
| SAM.gov | planned | Registered organizations and supplier identity context | planned organizations/suppliers |
| UN Comtrade | planned | Trade flow and commodity context | planned trade flows/commodities |

Source modules should live under `sources/<source_name>/` and expose contracts or
manifests that pipelines can consume without hard-coding source details into the
frontend.

Current source contracts:

- `sources/osm/source_contract.yml`
- `sources/osm/extract_manifest.yml`
- `sources/noaa/source_contract.yml`
- `sources/noaa/alerts_contract.yml`

Rules:

- Raw external payloads are stored in `raw_ingestions`.
- Derived sources such as `derived_risk_impacts` store evidence on the derived
  rows instead of duplicating upstream raw payloads.
- The map, tools, and chat layer consume canonical API/tool endpoints, not raw
  source tables.
