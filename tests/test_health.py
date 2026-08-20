import os

import pytest


def test_root_returns_200_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Tracked Systems" in response.text


def test_healthz_unauthenticated_200(client):
    response = client.get("/healthz")
    assert response.status_code == 200


def test_readyz_reports_udl_configured_boolean_only(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["udl_configured"] is True
    # Never leak the credentials themselves - only booleans and lengths
    assert "udl_username" not in body
    assert "udl_password" not in body
    assert body["udl_username_len"] == len("user")
    assert body["udl_password_len"] == len("pass")


def test_readyz_reports_team_token_boolean_and_length_not_value(client):
    response = client.get("/readyz")
    body = response.json()
    assert body["team_token_configured"] is True
    assert body["team_token_len"] == len("test-token")
    assert "team_token" not in body


def test_readyz_proves_storage_with_a_real_write(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["storage_writable"] is True
    assert "storage_error" not in body


@pytest.mark.skipif(
    os.geteuid() == 0,
    reason="root bypasses Unix permission bits, so this can't fail under a root "
    "test runner - only meaningful under the non-root uid the container actually "
    "runs as. This is an environment-scoped assertion, not a universal one.",
)
def test_readyz_returns_503_with_errno_when_storage_unwritable(
    fake_udl, tmp_path, monkeypatch
):
    from src.app import build_app
    from src.store import TrackedSystemsStore
    from tests.conftest import make_settings

    unwritable_dir = tmp_path / "readonly"
    unwritable_dir.mkdir()
    unwritable_dir.chmod(0o500)  # read+execute only, no write
    try:
        store = TrackedSystemsStore(seed_records=[])
        monkeypatch.setenv("STORAGE_MOUNT_PATH", str(unwritable_dir))
        app = build_app(
            settings=make_settings(), udl_client=fake_udl, systems_store=store
        )
        from fastapi.testclient import TestClient

        with TestClient(app) as test_client:
            response = test_client.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        assert body["storage_writable"] is False
        assert "storage_error" in body
        assert body["storage_error"]  # non-empty - the errno/message detail
    finally:
        unwritable_dir.chmod(0o700)  # restore so tmp_path cleanup can remove it


def test_version_endpoint_matches_the_packaged_version_file(client):
    from src._version import __version__

    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "udl-tactics-app"
    assert body["version"] == __version__
    assert body["version"] != "0.0.0-unknown"


def test_app_metadata_version_matches_version_module():
    from src._version import __version__
    from src.app import build_app

    app = build_app()
    assert app.version == __version__
