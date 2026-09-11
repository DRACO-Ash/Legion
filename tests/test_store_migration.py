"""Proof that schema 1 to 2 loses nothing.

The application is live. A migration that quietly drops a field on 49 real
records would be discovered by an analyst, not by a test, which is why this
file builds a store in the exact shape the shipped v0.9.2 code writes, using
the canonical seed data rather than a synthetic stand-in, and compares the
result field by field.
"""

from __future__ import annotations

import copy
import json
import uuid

from fastapi.testclient import TestClient

from src.app import build_app
from src.seed_data import SEED_RECORDS
from src.store import (
    SCHEMA_VERSION,
    STORE_FILENAME,
    TrackedSystemsStore,
    _add_compendium_layer,
)

from .conftest import make_settings

SEEDED_COUNT = 49
V1_STAMP = "2026-08-01T00:00:00.000Z"


def _write_v1_store(tmp_path) -> dict:
    """A store exactly as the shipped schema-1 code wrote it.

    Deliberately hand-built rather than produced by the current code: the
    point is to migrate a store written by the *old* shape, which the current
    code can no longer emit.
    """
    systems = {}
    for record in SEED_RECORDS:
        record_id = str(uuid.uuid4())
        systems[record_id] = {
            **record,
            "id": record_id,
            "archived": False,
            "created_at": V1_STAMP,
            "updated_at": V1_STAMP,
        }
    payload = {"schema_version": 1, "systems": systems}
    (tmp_path / STORE_FILENAME).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return copy.deepcopy(systems)


def _store_at(tmp_path, monkeypatch) -> TrackedSystemsStore:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    return TrackedSystemsStore(seed_records=SEED_RECORDS)


def test_all_49_records_survive_with_every_field_intact(tmp_path, monkeypatch) -> None:
    """The done bar for Phase 1, stated as a test."""
    before = _write_v1_store(tmp_path)
    store = _store_at(tmp_path, monkeypatch)

    after = {r["id"]: r for r in store.list(include_archived=True)}

    assert len(before) == SEEDED_COUNT
    assert set(after) == set(before)
    for record_id, original in before.items():
        assert after[record_id] == original, f"record {record_id} changed in migration"


def test_the_migration_adds_the_layer_and_leaves_records_alone(
    tmp_path, monkeypatch
) -> None:
    """The compendium hangs beside the catalogue, never inside a record."""
    before = _write_v1_store(tmp_path)
    store = _store_at(tmp_path, monkeypatch)
    store.list()  # trigger the read-side migration

    for record_id in before:
        layer = store.compendium_object(record_id)
        assert layer is not None, f"no compendium object for {record_id}"
        assert layer["system_id"] == record_id
        assert layer["capabilities"] == []
        assert layer["pol_segments"] == []
        assert layer["events"] == []
        assert layer["claims"] == []

    for record in store.list(include_archived=True):
        assert "compendium" not in record
        assert "capabilities" not in record


def test_the_migration_persists(tmp_path, monkeypatch) -> None:
    """The upgraded shape reaches disk on the next write."""
    _write_v1_store(tmp_path)
    store = _store_at(tmp_path, monkeypatch)

    first = store.list(include_archived=True)[0]
    store.update(first["id"], {"notes": "migration write"})

    on_disk = json.loads((tmp_path / STORE_FILENAME).read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == SCHEMA_VERSION
    assert len(on_disk["compendium"]["objects"]) == SEEDED_COUNT


def test_building_the_layer_twice_changes_nothing(tmp_path, monkeypatch) -> None:
    """Idempotency, tested where it actually lives.

    Two earlier versions of this test proved nothing. The first compared the
    store file before and after a second read, which compares the file with
    itself: a read migrates in memory and never writes. The second called
    _migrate twice, which cannot catch a non-idempotent layer builder either,
    because the schema_version guard makes the second call a no-op. So call
    the layer builder itself, twice, which is the thing that has to be safe to
    re-run.
    """
    _write_v1_store(tmp_path)
    _store_at(tmp_path, monkeypatch)

    raw = json.loads((tmp_path / STORE_FILENAME).read_text(encoding="utf-8"))
    _add_compendium_layer(raw)
    once = copy.deepcopy(raw)
    _add_compendium_layer(raw)

    assert raw == once, "re-running the layer builder altered the store"


def test_a_second_edit_does_not_clobber_the_first(tmp_path, monkeypatch) -> None:
    """update_compendium_object ensures the layer exists before merging. If
    that ensure step is not idempotent it silently discards everything already
    stored on the layer, which no single-write test can see."""
    _write_v1_store(tmp_path)
    store = _store_at(tmp_path, monkeypatch)
    target_id = store.list()[0]["id"]

    store.update_compendium_object(target_id, {"claims": [{"statement": "first"}]})
    store.update_compendium_object(target_id, {"pol_segments": [{"mode": "quiescent"}]})

    layer = store.compendium_object(target_id)
    assert layer["claims"] == [{"statement": "first"}], "the second write clobbered it"
    assert layer["pol_segments"] == [{"mode": "quiescent"}]


def test_a_live_compendium_edit_survives_a_later_read(tmp_path, monkeypatch) -> None:
    """The seed rule the catalogue already follows, applied to the new layer:
    never re-seed over a live edit."""
    _write_v1_store(tmp_path)
    store = _store_at(tmp_path, monkeypatch)
    target_id = store.list()[0]["id"]

    store.update_compendium_object(target_id, {"claims": [{"statement": "held"}]})
    assert store.compendium_object(target_id)["claims"] == [{"statement": "held"}]

    TrackedSystemsStore(seed_records=SEED_RECORDS).list()
    assert store.compendium_object(target_id)["claims"] == [{"statement": "held"}]


def test_the_catalogue_api_still_returns_the_49_unchanged(
    tmp_path, monkeypatch, fake_udl
) -> None:
    """The other half of the done bar: the shipped endpoint is untouched."""
    before = _write_v1_store(tmp_path)
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    app = build_app(
        settings=make_settings(),
        udl_client=fake_udl,
        systems_store=TrackedSystemsStore(seed_records=SEED_RECORDS),
    )
    with TestClient(app) as client:
        body = client.get("/api/systems", params={"include_archived": True}).json()

    assert body["count"] == SEEDED_COUNT
    served = {record["id"]: record for record in body["systems"]}
    for record_id, original in before.items():
        for field, value in original.items():
            assert served[record_id][field] == value, f"{field} changed on the wire"


def test_an_unknown_compendium_collection_is_refused(tmp_path, monkeypatch) -> None:
    """A typo in a collection name would otherwise create a silent orphan
    collection that nothing ever reads."""
    _write_v1_store(tmp_path)
    store = _store_at(tmp_path, monkeypatch)
    try:
        store.list_compendium("taktics")
        raise AssertionError("expected an unknown collection to be refused")
    except Exception as exc:  # noqa: BLE001 - the type is asserted on the next line
        assert "Unknown compendium collection" in str(exc)


def test_compendium_entities_round_trip_and_archive_rather_than_delete(
    tmp_path, monkeypatch
) -> None:
    """Create, read, anti-shrink update, archive. The same contract the
    catalogue already keeps, so a withdrawn assessment stays auditable."""
    _write_v1_store(tmp_path)
    store = _store_at(tmp_path, monkeypatch)

    created = store.create_compendium(
        "targets", {"id": "tgt-usa-314", "common_name": "USA 314", "operator": "US Gov"}
    )
    assert created["id"] == "tgt-usa-314"
    assert store.get_compendium("targets", "tgt-usa-314")["common_name"] == "USA 314"

    merged = store.update_compendium("targets", "tgt-usa-314", {"regime": "LEO"})
    assert merged["regime"] == "LEO"
    assert merged["operator"] == "US Gov", "anti-shrink merge cleared a field"

    store.archive_compendium("targets", "tgt-usa-314")
    assert store.list_compendium("targets") == []
    assert len(store.list_compendium("targets", include_archived=True)) == 1


def test_the_not_found_guards_return_none_rather_than_inventing(
    tmp_path, monkeypatch
) -> None:
    """The three guards, proved rather than assumed.

    The first is the one that matters most: a compendium object for a system
    that does not exist would be an orphan carrying provenance about nothing,
    and nothing would ever surface it again.
    """
    _write_v1_store(tmp_path)
    store = _store_at(tmp_path, monkeypatch)

    assert store.update_compendium_object("no-such-system", {"claims": []}) is None
    assert store.compendium_object("no-such-system") is None
    assert (
        store.update_compendium("targets", "no-such-target", {"regime": "GEO"}) is None
    )
    assert store.archive_compendium("targets", "no-such-target") is None
