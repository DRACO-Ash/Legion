"""Candidate systems: the posture rules, and the migration that lands them.

The catalogue's 49 records are a verbatim mirror of a delivered spreadsheet.
These seven are not, and the whole risk of adding them is that the difference
stops being visible. Every test here exists to keep it visible.

The migration is proved the way this repo has learned to prove one: by
breaking it on purpose first. Both sabotages below were run and both were
caught before these tests were trusted.
"""

from __future__ import annotations

import copy
import uuid

import pytest

from src.candidate_systems import CANDIDATE_FLAG, CANDIDATE_RECORDS
from src.satcat import load_extract
from src.seed_data import SEED_RECORDS
from src.store import CANDIDATE_KEY, _add_candidate_systems

CANONICAL_COUNT = 49


def _schema2_store() -> dict:
    """A store holding the canonical 49 and nothing else."""
    systems = {}
    for record in SEED_RECORDS:
        record_id = str(uuid.uuid4())
        systems[record_id] = {**record, "id": record_id, "archived": False}
    return {"schema_version": 2, "systems": systems, "compendium": {"objects": {}}}


def _keys(data: dict) -> list[str]:
    return [
        record[CANDIDATE_KEY]
        for record in data["systems"].values()
        if record.get(CANDIDATE_KEY)
    ]


# --- the posture ------------------------------------------------------------


@pytest.mark.parametrize("record", CANDIDATE_RECORDS, ids=lambda r: r["candidate_key"])
def test_a_candidate_catalogue_number_comes_from_the_snapshot(record) -> None:
    """The one field that could not be recalled.

    An invented NORAD id is the error in this domain that looks exactly like
    data: a chart plots the wrong satellite and looks entirely normal. These
    stayed empty until Ash supplied the SATCAT snapshot, and each is checked
    against it here, so a number that drifts fails rather than plotting.
    """
    row = load_extract().get(record["norad_id"])
    assert row is not None, f"{record['norad_id']} is not in the snapshot"
    assert row["launch_year"] == record["launch_year"]
    assert row["launch_site"] == record["launch_site"]


@pytest.mark.parametrize("record", CANDIDATE_RECORDS, ids=lambda r: r["candidate_key"])
def test_a_candidate_cites_its_source_and_names_who_verifies_it(record) -> None:
    """The claim rules, applied to the catalogue. An unverified entry that
    names nobody sits there for ever."""
    assert record["source_citation"].strip()
    assert record["verify_owner"].strip()
    assert record["flag"] == CANDIDATE_FLAG


def test_the_canonical_records_are_not_candidates() -> None:
    """If a spreadsheet row ever acquired a candidate key, the mirror would
    stop being checkable against the spreadsheet."""
    assert [r for r in SEED_RECORDS if r.get(CANDIDATE_KEY)] == []
    assert len(SEED_RECORDS) == CANONICAL_COUNT


def test_every_canonical_record_still_declares_a_launch_year() -> None:
    """`launch_year` was widened to optional for the candidates. That must not
    quietly become a hole in the catalogue proper."""
    missing = [r["catalogue_name"] for r in SEED_RECORDS if not r.get("launch_year")]
    assert missing == []


def test_candidate_keys_are_unique() -> None:
    keys = [r[CANDIDATE_KEY] for r in CANDIDATE_RECORDS]
    assert len(keys) == len(set(keys))


# --- the migration ----------------------------------------------------------


def test_the_migration_adds_every_candidate() -> None:
    data = _schema2_store()
    _add_candidate_systems(data, CANDIDATE_RECORDS)

    assert len(data["systems"]) == CANONICAL_COUNT + len(CANDIDATE_RECORDS)
    assert sorted(_keys(data)) == sorted(r[CANDIDATE_KEY] for r in CANDIDATE_RECORDS)
    for record in data["systems"].values():
        assert record["id"]


def test_running_the_migration_twice_adds_nothing() -> None:
    """Called directly, not through `_migrate`.

    Going through the migration would prove nothing: the `schema_version`
    guard makes the second call a no-op, so a non-idempotent builder passes.
    That exact mistake shipped in the schema-2 tests and was only caught by
    deliberately breaking the builder.
    """
    data = _schema2_store()
    _add_candidate_systems(data, CANDIDATE_RECORDS)
    once = copy.deepcopy(data)

    _add_candidate_systems(data, CANDIDATE_RECORDS)

    assert len(data["systems"]) == len(once["systems"])
    assert sorted(_keys(data)) == sorted(_keys(once))


def test_the_migration_leaves_every_existing_record_untouched() -> None:
    data = _schema2_store()
    before = copy.deepcopy(data["systems"])

    _add_candidate_systems(data, CANDIDATE_RECORDS)

    for record_id, original in before.items():
        assert data["systems"][record_id] == original


def test_an_edited_candidate_is_not_restored_to_its_original() -> None:
    """An analyst's edit outranks the shipped text. The key is all that is
    read, so a renamed or re-flagged candidate is matched and left alone."""
    data = _schema2_store()
    _add_candidate_systems(data, CANDIDATE_RECORDS)
    target = next(r for r in data["systems"].values() if r.get(CANDIDATE_KEY))
    target["notes"] = "analyst edit"
    target["archived"] = True

    _add_candidate_systems(data, CANDIDATE_RECORDS)

    assert target["notes"] == "analyst edit"
    assert target["archived"] is True
    assert len(_keys(data)) == len(CANDIDATE_RECORDS)


def test_a_candidate_gets_a_compendium_object_like_any_other_record() -> None:
    """Otherwise the claims API would 404 on a candidate, which is precisely
    the record most likely to need a claim attached."""
    data = _schema2_store()
    _add_candidate_systems(data, CANDIDATE_RECORDS)

    added = [r for r in data["systems"].values() if r.get(CANDIDATE_KEY)]
    for record in added:
        assert record["id"] in data["compendium"]["objects"]
