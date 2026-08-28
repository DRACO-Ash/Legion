"""Tests for the failure modes found in the first live deployment.

Legion 0.4.6 returned 500 on every read while `/readyz` reported healthy. The
App Store's file-storage add-on does not implement `rename`, so the store's
atomic write raised `OSError: [Errno 38] Function not implemented`, while the
readiness probe passed because a write-then-delete works fine on that mount.

Each test below pins one half of that: the store keeps working when the
filesystem refuses rename, and readiness stops claiming health when the store
cannot actually be loaded.
"""

from __future__ import annotations

import errno
import json
import os

import pytest
from fastapi.testclient import TestClient

from src.app import build_app
from src.store import TrackedSystemsStore

from .conftest import make_seed_record, make_settings

# Named once: the platform's SonarQube gate counts duplicated literals in the
# test tree as well as in src (sonar.tests=tests), and allows zero new issues.
ENOSYS_MESSAGE = "Function not implemented"

SEED = [
    make_seed_record(
        family_id="res-fam",
        family_title="Resilience Family",
        designator="RES-1",
        catalogue_name="RESSAT-1",
        launch_year=2024,
    )
]


@pytest.fixture
def no_rename(monkeypatch):
    """Simulate the add-on mount: rename is not implemented at all."""

    def refuse(src, dst):
        raise OSError(errno.ENOSYS, ENOSYS_MESSAGE, str(src))

    monkeypatch.setattr(os, "replace", refuse)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    return TrackedSystemsStore(seed_records=SEED)


def test_seeding_survives_a_filesystem_without_rename(store, tmp_path, no_rename):
    """The exact production failure: seeding must not raise."""
    records = store.list()
    assert len(records) == 1
    assert records[0]["catalogue_name"] == "RESSAT-1"

    on_disk = json.loads(
        (tmp_path / "tracked_systems.json").read_text(encoding="utf-8")
    )
    assert len(on_disk["systems"]) == 1


def test_writes_persist_without_rename(store, tmp_path, no_rename):
    """A create must survive a restart, not just return a record."""
    created = store.create({**SEED[0], "catalogue_name": "RESSAT-2"}, actor="1.2.3.4")

    reloaded = TrackedSystemsStore(seed_records=SEED)
    names = {r["catalogue_name"] for r in reloaded.list()}
    assert "RESSAT-2" in names
    assert created["id"] in {r["id"] for r in reloaded.list()}


def test_no_temp_file_is_left_behind(store, tmp_path, no_rename):
    store.list()
    assert not (tmp_path / "tracked_systems.json.tmp").exists()


def test_readiness_fails_when_the_store_cannot_be_loaded(store, monkeypatch):
    """The probe used to pass while every read returned 500."""

    def broken(self):
        raise OSError(errno.ENOSYS, ENOSYS_MESSAGE)

    monkeypatch.setattr(TrackedSystemsStore, "_read_raw", broken)
    writable, detail = store.probe_writable()
    assert writable is False
    assert "ENOSYS" in detail or ENOSYS_MESSAGE in detail


def test_readiness_passes_when_the_store_loads(store):
    writable, detail = store.probe_writable()
    assert writable is True
    assert detail == ""


def test_readyz_reports_not_ready_when_reads_would_fail(
    tmp_path, monkeypatch, fake_udl
):
    """End to end: readiness and the read path must agree."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))

    def broken(self):
        raise OSError(errno.ENOSYS, ENOSYS_MESSAGE)

    monkeypatch.setattr(TrackedSystemsStore, "_read_raw", broken)
    app = build_app(settings=make_settings(), udl_client=fake_udl)
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["storage_writable"] is False


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        # A valid body, so the request reaches the token gate rather than
        # stopping at FastAPI's own request-model validation.
        ("post", "/api/systems", dict(SEED[0])),
        ("patch", "/api/systems/x", {"notes": "unauthorised"}),
        ("delete", "/api/systems/x", None),
    ],
)
def test_writes_fail_closed_when_no_team_token_is_configured(
    method, path, body, tmp_path, monkeypatch, fake_udl
):
    """Unconfigured used to mean unauthenticated writes were accepted."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    app = build_app(settings=make_settings(team_token=None), udl_client=fake_udl)
    with TestClient(app) as client:
        kwargs = {} if body is None else {"json": body}
        response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 503
    assert "no team token" in response.json()["detail"]


def test_write_survives_a_temp_file_that_cannot_be_removed(
    store, tmp_path, no_rename, monkeypatch
):
    """The fallback must not fail because cleanup did.

    Covers the last uncovered branch of the write path: a filesystem that
    refuses rename may equally refuse unlink, and the store is written by then.
    """
    import pathlib

    def refuse_unlink(self, *args, **kwargs):
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(pathlib.Path, "unlink", refuse_unlink)
    records = store.list()
    assert len(records) == 1
    assert (tmp_path / "tracked_systems.json").exists()
