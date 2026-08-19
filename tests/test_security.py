from fastapi.testclient import TestClient

from src.app import build_app
from tests.conftest import FakeUDLClient, make_settings


def test_udl_route_401_without_token(client):
    response = client.get("/api/udl/jco-hrr", params={"common_name": "COSMOS-2612"})
    assert response.status_code == 401


def test_udl_route_200_with_valid_token(client, auth_headers):
    response = client.get("/api/udl/jco-hrr", params={"common_name": "COSMOS-2612"}, headers=auth_headers)
    assert response.status_code == 200


def test_udl_route_401_with_wrong_token(client):
    response = client.get(
        "/api/udl/jco-hrr", params={"common_name": "COSMOS-2612"}, headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


def test_health_routes_need_no_token(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_strict_rate_limit_returns_429_after_threshold(fake_udl):
    settings = make_settings()
    app = build_app(settings=settings, udl_client=fake_udl)
    with TestClient(app) as test_client:
        headers = {"Authorization": "Bearer test-token"}
        statuses = [
            test_client.get("/api/udl/jco-hrr", params={"common_name": "COSMOS-2612"}, headers=headers).status_code
            for _ in range(25)
        ]
    assert 429 in statuses


def test_no_wildcard_origin_with_token_configured():
    settings = make_settings(allowed_origin="*")
    try:
        build_app(settings=settings, udl_client=FakeUDLClient())
        assert False, "expected RuntimeError for wildcard origin with token set"
    except RuntimeError as exc:
        assert "ALLOWED_ORIGIN" in str(exc)
