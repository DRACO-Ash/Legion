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
    # Never leak the credentials themselves
    assert "udl_username" not in body
    assert "udl_password" not in body


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
