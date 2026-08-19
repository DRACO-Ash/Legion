import json
import os

import pytest

from src.store import TrackedSystemsStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    return TrackedSystemsStore(seed_records=[
        {
            "family_id": "test-fam",
            "family_title": "Test Family",
            "family_sub": "Test sub",
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
    ])


def test_seed_creates_store_file(store, tmp_path):
    records = store.list()
    assert len(records) == 1
    assert records[0]["catalogue_name"] == "TESTSAT-1"
    assert (tmp_path / "tracked_systems.json").exists()


def test_seed_is_idempotent_on_second_read(store, tmp_path):
    store.list()
    first_id = store.list()[0]["id"]
    # Re-instantiate against the same directory - must not re-seed over the existing file
    store2 = TrackedSystemsStore(seed_records=[])
    records = store2.list()
    assert len(records) == 1
    assert records[0]["id"] == first_id


def test_create_adds_a_record(store):
    created = store.create({
        "family_id": "new-fam", "family_title": "New", "family_sub": "sub",
        "nation": "CN", "designator": None, "catalogue_name": "NEWSAT",
        "launch_year": 2026, "launch_site": None, "norad_id": "99999",
        "regime": "GEO", "delta_v": None, "status": "unknown", "life": None,
        "coplanar": None, "notes": None, "flag": None,
    })
    assert created["id"]
    assert created["archived"] is False
    records = store.list()
    assert len(records) == 2


def test_update_anti_shrink_merge_keeps_unsent_fields(store):
    seeded = store.list()[0]
    updated = store.update(seeded["id"], {"status": "decayed"})
    assert updated["status"] == "decayed"
    # Fields not in the patch survive untouched
    assert updated["notes"] == "Seed record"
    assert updated["norad_id"] == "10001"


def test_update_missing_record_returns_none(store):
    assert store.update("does-not-exist", {"status": "decayed"}) is None


def test_archive_hides_record_by_default_but_keeps_it(store):
    seeded = store.list()[0]
    archived = store.archive(seeded["id"])
    assert archived["archived"] is True
    assert store.list() == []  # hidden by default
    assert len(store.list(include_archived=True)) == 1  # still present


def test_archive_missing_record_returns_none(store):
    assert store.archive("does-not-exist") is None


def test_archive_writes_a_backup(store, tmp_path):
    seeded = store.list()[0]
    store.archive(seeded["id"])
    backup_dir = tmp_path / "backups"
    assert backup_dir.exists()
    assert len(list(backup_dir.glob("*.bak"))) == 1


def test_filters_by_nation_regime_status_and_query(store):
    store.create({
        "family_id": "f2", "family_title": "F2", "family_sub": "s",
        "nation": "CN", "designator": None, "catalogue_name": "OTHERSAT",
        "launch_year": 2021, "launch_site": None, "norad_id": "20002",
        "regime": "GEO", "delta_v": None, "status": "decayed", "life": None,
        "coplanar": None, "notes": None, "flag": None,
    })
    assert len(store.list(nation="RU")) == 1
    assert len(store.list(regime="GEO")) == 1
    assert len(store.list(status="decayed")) == 1
    assert len(store.list(q="TESTSAT")) == 1
    assert len(store.list(nation="FR")) == 0


def test_list_sorted_by_launch_year(store):
    store.create({
        "family_id": "f2", "family_title": "F2", "family_sub": "s",
        "nation": "CN", "designator": None, "catalogue_name": "EARLYSAT",
        "launch_year": 1999, "launch_site": None, "norad_id": "1",
        "regime": "LEO", "delta_v": None, "status": "decayed", "life": None,
        "coplanar": None, "notes": None, "flag": None,
    })
    records = store.list()
    assert records[0]["catalogue_name"] == "EARLYSAT"


def test_store_file_is_valid_json_after_write(store, tmp_path):
    store.create({
        "family_id": "f3", "family_title": "F3", "family_sub": "s",
        "nation": "IR", "designator": None, "catalogue_name": "IRSAT",
        "launch_year": 2024, "launch_site": None, "norad_id": "30003",
        "regime": "LEO", "delta_v": None, "status": "unknown", "life": None,
        "coplanar": None, "notes": None, "flag": None,
    })
    path = tmp_path / "tracked_systems.json"
    with open(path) as fh:
        data = json.load(fh)
    assert data["schema_version"] == 1
    assert len(data["systems"]) == 2


def test_corrupt_store_file_falls_back_to_reseed(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    (tmp_path / "tracked_systems.json").write_text("not valid json{{{")
    store = TrackedSystemsStore(seed_records=[{
        "family_id": "f", "family_title": "F", "family_sub": "s", "nation": "RU",
        "designator": None, "catalogue_name": "X", "launch_year": 2020,
        "launch_site": None, "norad_id": None, "regime": "LEO", "delta_v": None,
        "status": "unknown", "life": None, "coplanar": None, "notes": None, "flag": None,
    }])
    records = store.list()
    assert len(records) == 1
