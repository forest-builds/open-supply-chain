NYC_HARBOR_BBOX = {
    "south": 40.35,
    "west": -74.45,
    "north": 41.05,
    "east": -73.55,
}

PORT_NEWARK_BBOX = {
    "south": 40.65,
    "west": -74.20,
    "north": 40.72,
    "east": -74.12,
}

NYC_METRO_BBOX = {
    "south": 39.75,
    "west": -75.65,
    "north": 41.65,
    "east": -71.85,
}

TRI_STATE_BBOX = {
    "south": 38.75,
    "west": -80.0,
    "north": 45.15,
    "east": -71.65,
}


def bbox_string(bbox: dict[str, float] = TRI_STATE_BBOX) -> str:
    return f"{bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']}"


def osm_ports_query(bbox: dict[str, float] = NYC_HARBOR_BBOX) -> str:
    bounds = bbox_string(bbox)
    return f"""
[out:json][timeout:180];
(
  nwr["seamark:type"="harbour"]({bounds});
  nwr["harbour"]({bounds});
  nwr["landuse"="port"]({bounds});
  nwr["industrial"="port"]({bounds});
  nwr["amenity"="ferry_terminal"]({bounds});
);
out center tags geom 5000;
"""


def osm_facilities_query(bbox: dict[str, float] = PORT_NEWARK_BBOX) -> str:
    bounds = bbox_string(bbox)
    return f"""
[out:json][timeout:180];
(
  nwr["industrial"="warehouse"]({bounds});
  nwr["man_made"="storage_tank"]({bounds});
  nwr["industrial"="logistics"]({bounds});
);
out center tags geom 5000;
"""


def osm_routes_query(bbox: dict[str, float] = NYC_HARBOR_BBOX) -> str:
    bounds = bbox_string(bbox)
    return f"""
[out:json][timeout:180];
(
  way["highway"~"motorway|trunk"]({bounds});
  way["railway"="rail"]({bounds});
  relation["route"="ferry"]({bounds});
);
out center tags geom 5000;
"""


def tri_state_supply_chain_query(
    bbox: dict[str, float] = NYC_HARBOR_BBOX,
    include_facilities: bool = False,
    include_routes: bool = False,
) -> str:
    if include_facilities and not include_routes:
        return osm_facilities_query(bbox)
    if include_routes and not include_facilities:
        return osm_routes_query(bbox)
    if include_facilities and include_routes:
        bounds = bbox_string(bbox)
        return f"""
[out:json][timeout:180];
(
  nwr["seamark:type"="harbour"]({bounds});
  nwr["harbour"]({bounds});
  nwr["landuse"="port"]({bounds});
  nwr["industrial"="port"]({bounds});
  nwr["amenity"="ferry_terminal"]({bounds});
  nwr["industrial"="warehouse"]({bounds});
  nwr["man_made"="storage_tank"]({bounds});
  nwr["industrial"="logistics"]({bounds});
  way["highway"~"motorway|trunk"]({bounds});
  way["railway"="rail"]({bounds});
  relation["route"="ferry"]({bounds});
);
out center tags geom 5000;
"""
    return osm_ports_query(bbox)
