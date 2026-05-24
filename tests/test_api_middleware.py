from fastapi.testclient import TestClient

from api.main import app


def test_health_includes_cors_headers_for_frontend_origin() -> None:
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_preflight_allows_geo_endpoint() -> None:
    client = TestClient(app)

    response = client.options(
        "/geo/entities?entity_type=port",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_favicon_returns_no_content() -> None:
    client = TestClient(app)

    response = client.get("/favicon.ico")

    assert response.status_code == 204
