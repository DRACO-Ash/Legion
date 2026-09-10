from fastapi.testclient import TestClient

from src.app import build_app
from src.udl_client import UDLError
from tests.conftest import FakeUDLClient, make_settings


def test_search_requires_common_name(client):
    response = client.get("/api/udl/jco-hrr")
    assert response.status_code == 400


def test_search_by_common_name_returns_normalised_record(client):
    response = client.get("/api/udl/jco-hrr", params={"common_name": "COSMOS-2612"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["sat_no"] == "68762"


def test_search_no_match_returns_empty_list(client):
    response = client.get(
        "/api/udl/jco-hrr",
        params={"common_name": "NOT-A-REAL-OBJECT"},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_get_by_sat_no_404_when_missing(client):
    response = client.get("/api/udl/jco-hrr/99999999")
    assert response.status_code == 404


def test_get_by_sat_no_200_when_present(client):
    response = client.get("/api/udl/jco-hrr/68763")
    assert response.status_code == 200
    assert response.json()["common_name"] == "COSMOS-2613"


def test_get_elset_404_when_missing(client):
    response = client.get("/api/udl/elset/68762")
    assert response.status_code == 404


def test_get_elset_200_when_present():
    fake = FakeUDLClient(
        satellites=[
            {
                "commonName": "COSMOS-2612",
                "satNo": "68762",
                "epoch": "2026-08-01T00:00:00.000000Z",
                "inclination": 65.0,
                "eccentricity": 0.01,
                "raan": 120.0,
                "argOfPerigee": 30.0,
                "meanAnomaly": 10.0,
                "meanMotion": 15.5,
                "classificationMarking": "U",
            }
        ]
    )
    app = build_app(settings=make_settings(), udl_client=fake)
    with TestClient(app) as test_client:
        response = test_client.get("/api/udl/elset/68762")
    assert response.status_code == 200
    assert response.json()["inclination"] == 65.0


def test_clash_check_reports_three_distinct_ids(client):
    response = client.get("/api/udl/clash-check")
    assert response.status_code == 200
    body = response.json()
    ids = {c["udl_sat_no"] for c in body["candidates"]}
    assert ids == {"68762", "68763", "68764"}
    assert "transcription error" in body["summary"]


def test_clash_check_flags_genuine_upstream_clash():
    fake = FakeUDLClient(
        satellites=[
            {
                "commonName": "COSMOS-2612",
                "satNo": "68762",
                "rank": 2,
                "orbitRegime": "LEO",
            },
            {
                "commonName": "COSMOS-2613",
                "satNo": "68762",
                "rank": 2,
                "orbitRegime": "LEO",
            },
            {
                "commonName": "COSMOS-2614",
                "satNo": "68762",
                "rank": 2,
                "orbitRegime": "LEO",
            },
        ]
    )
    app = build_app(settings=make_settings(), udl_client=fake)
    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/udl/clash-check", headers={"Authorization": "Bearer test-token"}
        )
    assert response.status_code == 200
    assert "genuine upstream ambiguity" in response.json()["summary"]


def test_clash_check_no_matches_says_so():
    fake = FakeUDLClient(satellites=[])
    app = build_app(settings=make_settings(), udl_client=fake)
    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/udl/clash-check", headers={"Authorization": "Bearer test-token"}
        )
    assert response.status_code == 200
    assert "no JCO HRR entries" in response.json()["summary"]


def test_udl_upstream_error_returns_502():
    fake = FakeUDLClient(raise_error=UDLError("boom"))
    app = build_app(settings=make_settings(), udl_client=fake)
    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/udl/jco-hrr",
            params={"common_name": "COSMOS-2612"},
        )
    assert response.status_code == 502
    # Never leak the raw upstream error message. The detail is built from the
    # fault kind, not from the exception's text, so this holds even though the
    # response now names the cause.
    assert "boom" not in response.text
    detail = response.json()["detail"]
    assert "connection to UDL failed" in detail
    assert "/api/udl/diagnostics" in detail


def test_a_502_names_the_kind_of_fault():
    """A deployment sat on "UDL did not answer" with no way to tell a wrong
    password from a blocked egress path. The status is the discriminator and
    it now reaches the caller."""
    fake = FakeUDLClient(raise_error=UDLError("nope", status_code=401))
    app = build_app(settings=make_settings(), udl_client=fake)
    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/udl/jco-hrr", params={"common_name": "COSMOS-2612"}
        )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "rejected the credentials" in detail
    assert "HTTP 401" in detail
    assert "nope" not in detail


def test_udl_not_configured_returns_503():
    fake = FakeUDLClient(configured=False)
    app = build_app(settings=make_settings(), udl_client=fake)
    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/udl/jco-hrr",
            params={"common_name": "COSMOS-2612"},
        )
    assert response.status_code == 503
