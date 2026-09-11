"""The pattern-of-life layer: vocabulary, epochs, and the seeded history.

The two rules worth the most here are structural. A mode the model calls
instantaneous must never be drawn as a band, and an epoch must never be more
precise on screen than it was in the source. Both invent something the data
does not contain, which is the failure this whole layer exists to prevent.
"""

from __future__ import annotations

import copy
import uuid

import pytest

from src.compendium_models import INSTANTANEOUS_MODES, MODES_NEEDING_COUNTERPART
from src.pol import modes, parse_pol_epoch
from src.pol_seed import SEED_SEGMENTS, TARGET_PREFIX
from src.store import POL_SEGMENTS, SEED_KEY, _add_pol_segments


def _store_with(names: list[str]) -> dict:
    systems = {}
    for name in names:
        record_id = str(uuid.uuid4())
        systems[record_id] = {"id": record_id, "catalogue_name": name}
    return {
        "schema_version": 3,
        "systems": systems,
        "compendium": {"objects": {}},
    }


def _all_segments(data: dict) -> list[dict]:
    return [
        segment
        for layer in data["compendium"]["objects"].values()
        for segment in layer.get(POL_SEGMENTS, [])
    ]


# --- the served vocabulary --------------------------------------------------


def test_the_vocabulary_covers_every_declared_mode() -> None:
    """A mode the model accepts but the legend cannot explain would reach an
    analyst as a bare identifier."""
    served = modes()["modes"]
    for entry in served:
        assert entry["label"] and entry["meaning"]
    assert len(served) == 12


def test_the_vocabulary_reads_its_structure_from_the_model() -> None:
    """Restating which modes are instants would let the two drift, and the
    interface would draw a duration the data does not have."""
    served = {entry["value"]: entry for entry in modes()["modes"]}
    instants = {v for v, e in served.items() if e["instantaneous"]}
    counterpart = {v for v, e in served.items() if e["needs_counterpart"]}

    assert instants == set(INSTANTANEOUS_MODES)
    assert counterpart == set(MODES_NEEDING_COUNTERPART)


def test_observability_is_served_separately_from_confidence() -> None:
    """Different questions: how well it could be seen, against how sure we
    are the assessment is right."""
    served = modes()
    assert {e["value"] for e in served["observability"]} == {
        "dense",
        "moderate",
        "sparse",
        "unknown",
    }


# --- epoch precision --------------------------------------------------------


@pytest.mark.parametrize(
    ("epoch", "expected", "precision"),
    [
        ("2024", "2024-01-01", "year"),
        ("2024-05", "2024-05-01", "month"),
        ("2024-05-17", "2024-05-17", "day"),
    ],
)
def test_an_epoch_reports_the_precision_it_actually_carries(
    epoch, expected, precision
) -> None:
    assert parse_pol_epoch(epoch) == (expected, precision)


@pytest.mark.parametrize("epoch", ["", "2024-5", "May 2024", "2024-05-17T00:00:00Z"])
def test_an_unparseable_epoch_is_visibly_odd_rather_than_coerced(epoch) -> None:
    """Silently coercing a hand-entered epoch would place a band at a date
    nobody chose."""
    placed, precision = parse_pol_epoch(epoch)
    assert precision == "unrecognised"
    assert placed == epoch.strip()


# --- the seeded history -----------------------------------------------------


def test_every_seeded_segment_names_a_counterpart_when_its_mode_requires_one() -> None:
    offenders = [
        seed["seed_key"]
        for seed in SEED_SEGMENTS
        if seed["mode"] in MODES_NEEDING_COUNTERPART and not seed["related_name"]
    ]
    assert offenders == []


def test_every_seeded_segment_carries_a_sourced_claim() -> None:
    """A segment is an assessment, not an observation. Unsourced, it would
    read on the timeline exactly like a sourced one."""
    for seed in SEED_SEGMENTS:
        claim = seed["claim"]
        assert claim["source_citation"].strip()
        assert claim["asserted_by"].strip()
        assert claim["marker"] in {"FACT", "INFERENCE", "SPECULATION"}


def test_no_seeded_epoch_is_more_precise_than_a_day() -> None:
    """Guards against someone later pasting a full timestamp the source
    cannot support."""
    for seed in SEED_SEGMENTS:
        for field in ("start_epoch", "end_epoch"):
            value = seed.get(field)
            if value:
                assert parse_pol_epoch(value)[1] != "unrecognised", seed["seed_key"]


def test_seed_keys_are_unique() -> None:
    keys = [seed["seed_key"] for seed in SEED_SEGMENTS]
    assert len(keys) == len(set(keys))


# --- the migration ----------------------------------------------------------


def test_a_counterpart_we_hold_resolves_to_its_system_id() -> None:
    data = _store_with(["SJ-21", "SJ-25"])
    _add_pol_segments(data, SEED_SEGMENTS)

    ids = {r["catalogue_name"]: r["id"] for r in data["systems"].values()}
    pair = [s for s in _all_segments(data) if s["mode"] == "rpo_shadowing"]
    assert {s["related_object_id"] for s in pair} == {ids["SJ-21"], ids["SJ-25"]}


def test_a_counterpart_we_do_not_hold_keeps_its_slug() -> None:
    """USA 314 is not one of our systems. Resolving it to something shaped
    like a catalogue id would put a phantom object in the graph."""
    data = _store_with(["COSMOS-2576"])
    _add_pol_segments(data, SEED_SEGMENTS)

    segment = _all_segments(data)[0]
    assert segment["related_object_id"].startswith(TARGET_PREFIX)


def test_a_seed_naming_an_object_the_store_lacks_is_skipped() -> None:
    """A hand-pruned catalogue stays consistent rather than gaining an
    orphaned timeline."""
    data = _store_with(["SJ-21"])
    _add_pol_segments(data, SEED_SEGMENTS)

    assert {s["object_id"] for s in _all_segments(data)} == set(data["systems"])


def test_running_the_seeding_twice_adds_nothing() -> None:
    """Called directly, not through `_migrate`: the schema guard would make
    the second call a no-op and prove nothing. That mistake shipped once."""
    data = _store_with(["SJ-21", "SJ-25", "COSMOS-2576"])
    _add_pol_segments(data, SEED_SEGMENTS)
    once = copy.deepcopy(_all_segments(data))

    _add_pol_segments(data, SEED_SEGMENTS)

    assert len(_all_segments(data)) == len(once)
    assert [s[SEED_KEY] for s in _all_segments(data)] == [s[SEED_KEY] for s in once]


def test_an_edited_segment_is_not_restored_to_its_seeded_text() -> None:
    data = _store_with(["SJ-21"])
    _add_pol_segments(data, SEED_SEGMENTS)
    target = _all_segments(data)[0]
    target["notes"] = "analyst edit"

    _add_pol_segments(data, SEED_SEGMENTS)

    assert _all_segments(data)[0]["notes"] == "analyst edit"


# --- the three bugs a browser found, pinned --------------------------------


def _timeline(segments: list[dict], names: dict[str, str] | None = None) -> dict:
    from src.pol import build_timeline

    return build_timeline(segments, names)


def _segment(mode: str, start: str, **extra) -> dict:
    body = {"mode": mode, "start_epoch": start, "claim": {"marker": "FACT"}}
    body.update(extra)
    return body


def test_an_instant_has_no_end_at_all() -> None:
    """It read "2024 to ongoing" in the browser, which asserts a behaviour
    still happening. A burn is a point in time."""
    placed = _timeline([_segment("anomalous_high_dv", "2024")])["segments"][0]

    assert placed["instantaneous"] is True
    assert placed["end"] is None
    assert placed["end_precision"] == "instant"


def test_a_missing_end_is_recorded_as_open_not_ongoing() -> None:
    """SJ-21's 2022 capture is finished. It read as ongoing purely because
    no end was recorded, and a blank field is not evidence of continuation."""
    placed = _timeline([_segment("rpo_docking", "2022", related_object_id="x")])
    assert placed["segments"][0]["end_precision"] == "open"


def test_a_counterpart_is_named_by_the_server_not_looked_up_in_the_browser() -> None:
    """The interface holds only the page of the catalogue on screen, so a
    filtered-out counterpart rendered as a raw uuid."""
    placed = _timeline(
        [_segment("rpo_shadowing", "2025-01", related_object_id="abc-123")],
        {"abc-123": "SJ-21"},
    )["segments"][0]

    assert placed["counterpart"] == {
        "id": "abc-123",
        "label": "SJ-21",
        "in_catalogue": True,
    }


def test_a_counterpart_outside_the_catalogue_says_so() -> None:
    placed = _timeline(
        [_segment("rpo_shadowing", "2024-05", related_object_id="target:usa-314")]
    )["segments"][0]

    assert placed["counterpart"]["in_catalogue"] is False
    assert placed["counterpart"]["label"] == "usa 314"


def test_a_single_dated_history_still_places_its_segment() -> None:
    """One point on an axis of zero width would divide by zero."""
    built = _timeline([_segment("quiescent", "2024")])
    assert built["count"] == 1
    assert built["segments"][0]["offset_pct"] == 0.0


def test_segments_come_back_sorted_by_when_they_started() -> None:
    built = _timeline(
        [_segment("quiescent", "2025-06"), _segment("station_keeping", "2024-01")]
    )
    assert [s["start_epoch"] for s in built["segments"]] == ["2024-01", "2025-06"]
