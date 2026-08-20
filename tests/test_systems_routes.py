import pytest
from fastapi.testclient import TestClient

from src.app import build_app
from src.store import TrackedSystemsStore
from tests.conftest import make_settings


@pytest.fixture
def systems_client(tmp_path, monkeypatch, fake_udl):
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    seed = [
        {
            "family_id": "test-fam",
            "family_title": "Test Family",
            "family_sub": "sub",
            "nation": "RU",
            "designator": "Test-1",
            "catalogue_name": "TESTSAT-1",
            "launch_year": 2020,
            "launch_site": None,
            "norad_id": "10001",
            "regime": "LEO",
            "delta_v": None,
            "status": "onorbit",
            "life": None,
            "coplanar": None,
            "notes": "Seed record",
            "flag": None,
        }
    ]
    store = TrackedSystemsStore(seed_records=seed)
    app = build_app(settings=make_settings(), udl_client=fake_udl, systems_store=store)
    with TestClient(app) as test_client:
        yield test_client


def test_list_is_public_no_token_needed(systems_client):
    response = systems_client.get("/api/systems")
    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_get_by_id(systems_client):
    seeded_id = systems_client.get("/api/systems").json()["systems"][0]["id"]
    response = systems_client.get(f"/api/systems/{seeded_id}")
    assert response.status_code == 200
    assert response.json()["catalogue_name"] == "TESTSAT-1"


def test_get_missing_id_404(systems_client):
    response = systems_client.get("/api/systems/does-not-exist")
    assert response.status_code == 404


def test_create_requires_token(systems_client):
    payload = {
        "family_id": "f2",
        "family_title": "F2",
        "family_sub": "s",
        "nation": "CN",
        "catalogue_name": "NEWSAT",
        "launch_year": 2026,
        "regime": "GEO",
    }
    response = systems_client.post("/api/systems", json=payload)
    assert response.status_code == 401


def test_create_with_valid_token(systems_client, auth_headers):
    payload = {
        "family_id": "f2",
        "family_title": "F2",
        "family_sub": "s",
        "nation": "CN",
        "catalogue_name": "NEWSAT",
        "launch_year": 2026,
        "regime": "GEO",
    }
    response = systems_client.post("/api/systems", json=payload, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["catalogue_name"] == "NEWSAT"
    assert body["status"] == "unknown"  # default applied
    assert systems_client.get("/api/systems").json()["count"] == 2


def test_create_rejects_malformed_payload(systems_client, auth_headers):
    # missing required fields (catalogue_name, launch_year, regime, etc.)
    response = systems_client.post(
        "/api/systems", json={"nation": "CN"}, headers=auth_headers
    )
    assert response.status_code == 422


def test_update_requires_token(systems_client):
    seeded_id = systems_client.get("/api/systems").json()["systems"][0]["id"]
    response = systems_client.patch(
        f"/api/systems/{seeded_id}", json={"status": "decayed"}
    )
    assert response.status_code == 401


def test_update_anti_shrink_via_route(systems_client, auth_headers):
    seeded_id = systems_client.get("/api/systems").json()["systems"][0]["id"]
    response = systems_client.patch(
        f"/api/systems/{seeded_id}", json={"status": "decayed"}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "decayed"
    assert body["notes"] == "Seed record"  # untouched


def test_update_missing_id_404(systems_client, auth_headers):
    response = systems_client.patch(
        "/api/systems/does-not-exist", json={"status": "decayed"}, headers=auth_headers
    )
    assert response.status_code == 404


def test_archive_requires_token(systems_client):
    seeded_id = systems_client.get("/api/systems").json()["systems"][0]["id"]
    response = systems_client.delete(f"/api/systems/{seeded_id}")
    assert response.status_code == 401


def test_archive_hides_by_default(systems_client, auth_headers):
    seeded_id = systems_client.get("/api/systems").json()["systems"][0]["id"]
    response = systems_client.delete(f"/api/systems/{seeded_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["archived"] is True
    assert systems_client.get("/api/systems").json()["count"] == 0
    assert systems_client.get("/api/systems?include_archived=true").json()["count"] == 1


def test_archive_missing_id_404(systems_client, auth_headers):
    response = systems_client.delete(
        "/api/systems/does-not-exist", headers=auth_headers
    )
    assert response.status_code == 404


def test_filter_by_query_param(systems_client):
    response = systems_client.get("/api/systems", params={"q": "TESTSAT"})
    assert response.json()["count"] == 1
    response = systems_client.get("/api/systems", params={"q": "NOTHINGMATCHESTHIS"})
    assert response.json()["count"] == 0
