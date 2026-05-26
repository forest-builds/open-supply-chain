# Supply Chain Examples

## Refrigerated Food Imports Through Port Newark

This is the first concrete, named chain trace:

```text
Observed cargo/tanker vessels near Port Newark
  -> Port Newark / near-Newark port entity
  -> SERVED_BY_ROUTE corridor edges
  -> warehouse, logistics, storage, or cold/food keyword facilities sharing those routes
```

Query it through the API:

```bash
curl "http://localhost:8000/chains/examples/refrigerated-food-port-newark?radius_km=8&limit=10"
```

Or through MCP/tool catalog as:

```text
example_refrigerated_food_port_newark
```

The response includes an anchor port, serving routes, facility peers, AIS cargo
or tanker vessels near the port, flow steps, confidence, and limitations.

Important caveat: this is an evidence trace, not a cargo manifest. AIS vessel
positions and OSM route/facility adjacency can show plausible movement through
the regional graph, but they do not prove a specific refrigerated shipment.

## Why Not Jet Fuel To JFK Yet?

That chain should exist next, but it needs a new source before it can be honest:
our current EIA pipeline loads power plants, not petroleum terminals. A grown-up
jet-fuel trace needs petroleum terminal or product movement data, route/pipe or
truck handoff, airport fuel-farm linkage, and potentially tanker/barges where
available.
