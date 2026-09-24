"""The API must stay up and explain itself when the database is not configured."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(no_database):
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_health_reports_degraded(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["data"]["status"] == "degraded"
    assert body["data"]["database"]["status"] == "not_configured"


@pytest.mark.parametrize("path", ["/api/firms", "/api/hotspots", "/api/clusters", "/api/incidents", "/api/alerts", "/api/facilities"])
def test_data_endpoints_return_consistent_503(client, path):
    r = client.get(path)
    assert r.status_code == 503
    assert r.json() == {
        "status": "error",
        "error": {"code": "database_not_configured", "message": r.json()["error"]["message"], "details": None},
    }


def test_map_config_and_india_boundary_available(client):
    cfg = client.get("/api/map/config").json()["data"]
    assert cfg["region"]["name"] == "India"
    assert "India" in cfg["region"]["boundary"]["land"]
    boundary = client.get("/api/map/boundary").json()["data"]
    assert {f["properties"]["role"] for f in boundary["features"]} == {"mask", "monitoring_area", "land"}


def test_data_sources_lists_every_source(client):
    ids = {s["id"] for s in client.get("/api/data-sources").json()["data"]}
    assert {"nasa_firms", "osm_overpass", "esa_worldcover", "ne_india_boundary", "marineregions_eez", "database"} <= ids


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["status"] == "error"


def test_openapi_documents_required_endpoints(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    for p in ["/api/health", "/api/firms", "/api/facilities", "/api/hotspots", "/api/clusters", "/api/incidents", "/api/alerts", "/api/data-sources"]:
        assert p in paths
