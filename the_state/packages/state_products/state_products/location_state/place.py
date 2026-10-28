from __future__ import annotations

from dataclasses import dataclass

US_STATE_CODES: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "PR",
        "VI",
        "GU",
        "AS",
        "MP",
    }
)

STATE_NAME_TO_CODE: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "puerto rico": "PR",
    "virgin islands": "VI",
    "guam": "GU",
    "american samoa": "AS",
    "northern mariana islands": "MP",
}

CODE_TO_STATE_NAME: dict[str, str] = {v: k.title() for k, v in STATE_NAME_TO_CODE.items()}

NYC_ALIASES: frozenset[str] = frozenset({"nyc", "new york city"})

NYC_BOROUGH_ALIASES: dict[str, str] = {
    "manhattan": "MANHATTAN",
    "new york county": "MANHATTAN",
    "bronx": "BRONX",
    "the bronx": "BRONX",
    "brooklyn": "BROOKLYN",
    "kings county": "BROOKLYN",
    "queens": "QUEENS",
    "queens county": "QUEENS",
    "staten island": "STATEN ISLAND",
    "richmond county": "STATEN ISLAND",
}


@dataclass(frozen=True)
class Place:
    raw: str
    locality: str | None
    state_code: str | None
    borough: str | None = None

    @property
    def state_name(self) -> str | None:
        return CODE_TO_STATE_NAME.get(self.state_code) if self.state_code else None


def parse_place(raw: str) -> Place:
    """Parse a place string into a Place.

    Supports:
    - "New York, NY" -> locality="New York", state_code="NY"
    - "NYC"          -> locality="New York", state_code="NY"
    - "Brooklyn, NYC"-> locality="New York", state_code="NY", borough="BROOKLYN"
    - "NY"           -> locality=None,       state_code="NY"
    - "New York"     -> locality="New York", state_code="NY" (state name lookup)
    - "California"   -> locality=None,       state_code="CA"

    Unknown places return Place(raw, None, None). Callers decide whether to 404.
    """
    if not raw or not raw.strip():
        return Place(raw=raw, locality=None, state_code=None)

    cleaned = raw.strip()
    cleaned_lower = cleaned.lower()

    if cleaned_lower in NYC_ALIASES:
        return Place(raw=raw, locality="New York", state_code="NY")

    borough = _resolve_nyc_borough(cleaned)
    if borough is not None:
        return Place(raw=raw, locality="New York", state_code="NY", borough=borough)

    if "," in cleaned:
        head, tail = (part.strip() for part in cleaned.split(",", 1))
        tail_lower = tail.lower()
        if tail_lower in NYC_ALIASES:
            borough = _resolve_nyc_borough(head)
            locality = "New York" if borough else head or "New York"
            return Place(raw=raw, locality=locality, state_code="NY", borough=borough)

        state_code = _resolve_state_token(tail)
        locality = head or None
        borough = _resolve_nyc_borough(head) if state_code == "NY" else None
        if borough is not None:
            locality = "New York"
        return Place(raw=raw, locality=locality, state_code=state_code, borough=borough)

    state_code = _resolve_state_token(cleaned)
    if state_code is not None:
        # Whole input resolved to a state (code or full name); no locality.
        return Place(raw=raw, locality=None, state_code=state_code)

    return Place(raw=raw, locality=cleaned, state_code=None)


def _resolve_state_token(token: str) -> str | None:
    upper = token.strip().upper()
    if upper in US_STATE_CODES:
        return upper
    return STATE_NAME_TO_CODE.get(token.strip().lower())


def _resolve_nyc_borough(token: str) -> str | None:
    return NYC_BOROUGH_ALIASES.get(token.strip().lower())
