from fastapi.testclient import TestClient

from src.app import build_app
from tests.conftest import FakeUDLClient, make_settings


def test_udl_route_needs_no_token(client):
    """The UDL routes are open. This is the deliberate 0.9.0 decision.

    A shared bearer token used to gate them. It was removed because it cost
    more operator time to diagnose than it protected, and because it gated
    the element-set lookups the application exists to serve. Access control
    is the platform's, in front of this app. If this test ever starts
    asserting a 401 again, that has to be a decision someone took, not a
    dependency that crept back in.
    """
    response = client.get("/api/udl/jco-hrr", params={"common_name": "COSMOS-2612"})
    assert response.status_code == 200


def test_a_stray_authorization_header_changes_nothing(client):
    """Nothing reads the header any more, so a leftover one is inert rather
    than a 401. A browser tab that still holds an old token must not break."""
    response = client.get(
        "/api/udl/jco-hrr",
        params={"common_name": "COSMOS-2612"},
        headers={"Authorization": "Bearer whatever-this-is"},
    )
    assert response.status_code == 200


def test_writes_need_no_token(client):
    """Writes are open too, and openly so. The catalogue is public-domain
    reference data; the control that matters is the platform in front."""
    created = client.post(
        "/api/systems",
        json={
            "family_id": "chn-sj",
            "family_title": "Shijian (SJ) Programme",
            "family_sub": "GEO servicing and RPO",
            "nation": "CN",
            "catalogue_name": "TEST-OPEN-WRITE",
            "launch_year": 2026,
            "regime": "GEO",
        },
    )
    assert created.status_code == 201


def test_health_routes_need_no_token(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_no_token_endpoint_survives(client):
    """/api/token-check went with the token it diagnosed."""
    assert client.get("/api/token-check").status_code == 404


def test_strict_rate_limit_returns_429_after_threshold(fake_udl):
    """The limiter is now the only control on the UDL call budget, so it
    matters more than it did, not less."""
    settings = make_settings()
    app = build_app(settings=settings, udl_client=fake_udl)
    with TestClient(app) as test_client:
        statuses = [
            test_client.get(
                "/api/udl/jco-hrr",
                params={"common_name": "COSMOS-2612"},
            ).status_code
            for _ in range(25)
        ]
    assert 429 in statuses


def test_wildcard_origin_always_refuses_to_start():
    """Unconditional now. It used to be conditional on a team token being
    set, which was the wrong way round: with no application-level gate on
    writes, a wildcard origin would let any page on the internet issue them
    from a reader's browser."""
    settings = make_settings(allowed_origin="*")
    try:
        build_app(settings=settings, udl_client=FakeUDLClient())
        raise AssertionError("expected RuntimeError for a wildcard origin")
    except RuntimeError as exc:
        assert "ALLOWED_ORIGIN" in str(exc)
