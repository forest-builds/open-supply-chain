from pipelines.impact_network import ensure_source, rebuild_risk_impacts


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "RETURNING id::text" in query:
            return FakeCursor({"id": "source-1"})
        if "count(*)::int AS count FROM risk_impacts" in query:
            return FakeCursor({"count": 7})
        return FakeCursor({})


def test_ensure_source_upserts_derived_source() -> None:
    conn = FakeConnection()

    source_id = ensure_source(
        conn,
        name="derived_risk_impacts",
        api_url="postgres://risk_events+geo_entities",
        auth_required=False,
        refresh_rate="after risk/entity ingestion",
        metadata={"derived_from": ["risk_events", "geo_entities"]},
    )

    assert source_id == "source-1"
    assert "ON CONFLICT (name)" in conn.calls[0][0]
    assert conn.calls[0][1][0] == "derived_risk_impacts"


def test_rebuild_risk_impacts_uses_bounded_spatial_rule() -> None:
    conn = FakeConnection()

    count = rebuild_risk_impacts(conn, source_id="source-1", near_distance_m=500)

    query, params = conn.calls[0]
    assert count == 7
    assert "risk_events re" in query
    assert "geo_entities ge" in query
    assert "ST_Intersects" in query
    assert "ST_DWithin" in query
    assert "ST_Expand" in query
    assert params[0] == 500
    assert params[1] == ["port", "facility", "route"]
    assert params[2] == 500 / 111_320
