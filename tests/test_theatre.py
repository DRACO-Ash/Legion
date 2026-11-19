"""The theatre: every assessed behaviour on one axis, and a narrow overlap rule.

The view exists to show co-occurrence across objects, so the overlap rule is
where it can mislead. A behaviour with no recorded end is the dangerous case:
counted to the axis end, one blank field in 2021 would "share a period" with
everything recorded since. These tests hold that rule on synthetic data, then
check it reproduces the one co-occurrence the sources do describe.
"""

from __future__ import annotations

import re
from datetime import date

from src.ranking_policy import FORBIDDEN_FIELDS
from src.theatre import OVERLAP_RULE, build_theatre

from .conftest import make_seed_record
from .test_ui_contracts import INDEX_HTML


def _record(record_id: str, name: str, **overrides) -> dict:
    return make_seed_record(id=record_id, catalogue_name=name, **overrides)


def _segment(seg_id: str, start: str, end: str | None = None, **overrides) -> dict:
    return {
        "id": seg_id,
        "mode": overrides.pop("mode", "rpo_inspection"),
        "start_epoch": start,
        "end_epoch": end,
        "claim": {"marker": "FACT", "statement": seg_id},
        **overrides,
    }


def _theatre(*objects: tuple[dict, list[dict]]) -> dict:
    records = [record for record, _ in objects]
    layers = {record["id"]: {"pol_segments": segments} for record, segments in objects}
    return build_theatre(records, layers)


def _segments(theatre: dict) -> dict:
    return {
        segment["id"]: segment
        for lane in theatre["lanes"]
        for row in lane["rows"]
        for segment in row["segments"]
    }


def _served(client) -> dict:
    response = client.get("/api/theatre")
    assert response.status_code == 200, response.json()
    return response.json()


def test_a_blank_end_never_invents_a_shared_period():
    """The case the rule exists for. Counted to the axis end, A (2021, no end
    recorded) would share a period with B (2024), and nothing says it should."""
    theatre = _theatre(
        (_record("a", "Alpha"), [_segment("a1", "2021")]),
        (_record("b", "Bravo"), [_segment("b1", "2024-05")]),
    )
    segments = _segments(theatre)
    assert segments["a1"]["shared_period"] == []
    assert segments["b1"]["shared_period"] == []
    assert segments["a1"]["extent"] == {"from": "2021-01-01", "to": "2021-12-31"}


def test_a_date_covers_the_period_it_was_recorded_at():
    """A year-only date fills the year; a month-only date fills the month."""
    theatre = _theatre(
        (_record("a", "Alpha"), [_segment("a1", "2024")]),
        (_record("b", "Bravo"), [_segment("b1", "2024-05", "2025-02")]),
        (_record("c", "Charlie"), [_segment("c1", "2024-02")]),
    )
    segments = _segments(theatre)
    assert segments["a1"]["extent"]["to"] == "2024-12-31"
    assert segments["b1"]["extent"] == {"from": "2024-05-01", "to": "2025-02-28"}
    assert segments["c1"]["extent"]["to"] == "2024-02-29", "2024 is a leap year"


def test_sharing_is_symmetric_and_never_with_the_same_object():
    theatre = _theatre(
        (_record("a", "Alpha"), [_segment("a1", "2024"), _segment("a2", "2024-06")]),
        (_record("b", "Bravo"), [_segment("b1", "2024-06")]),
    )
    segments = _segments(theatre)
    assert segments["a1"]["shared_period"] == ["b1"]
    assert segments["a2"]["shared_period"] == ["b1"]
    assert sorted(segments["b1"]["shared_period"]) == ["a1", "a2"]


def test_what_is_drawn_is_what_is_counted():
    """A band's position and width are its extent on the axis, nothing more,
    so the picture cannot disagree with the shared-period list beside it."""
    theatre = _theatre(
        (_record("a", "Alpha"), [_segment("a1", "2021")]),
        (_record("b", "Bravo"), [_segment("b1", "2025-03")]),
    )
    lo = date.fromisoformat(theatre["span"]["from"])
    hi = date.fromisoformat(theatre["span"]["to"])
    days = (hi - lo).days + 1
    for segment in _segments(theatre).values():
        start = date.fromisoformat(segment["extent"]["from"])
        end = date.fromisoformat(segment["extent"]["to"])
        assert segment["x_pct"] == round(100.0 * (start - lo).days / days, 4)
        assert segment["w_pct"] == round(100.0 * ((end - start).days + 1) / days, 4)


def test_the_axis_runs_to_the_end_of_the_latest_recorded_period():
    """It once ended at the latest start, which drew every behaviour recorded
    in the final month at zero width on the right edge."""
    theatre = _theatre(
        (_record("a", "Alpha"), [_segment("a1", "2021")]),
        (_record("b", "Bravo"), [_segment("b1", "2025-03")]),
    )
    assert theatre["span"] == {"from": "2021-01-01", "to": "2025-03-31"}
    for segment in _segments(theatre).values():
        assert segment["w_pct"] > 0
        assert 0 <= segment["x_pct"] and segment["x_pct"] + segment["w_pct"] <= 100.0001


def test_an_instant_is_placed_but_never_reads_as_open():
    theatre = _theatre(
        (_record("a", "Alpha"), [_segment("a1", "2023-12", mode="separation_event")]),
    )
    segment = _segments(theatre)["a1"]
    assert segment["instantaneous"] is True
    assert segment["end_precision"] == "instant"


def test_archived_records_and_segments_are_left_out():
    theatre = _theatre(
        (_record("a", "Alpha"), [_segment("a1", "2024", archived=True)]),
        (_record("b", "Bravo", archived=True), [_segment("b1", "2024")]),
        (_record("c", "Charlie"), [_segment("c1", "2024")]),
    )
    assert set(_segments(theatre)) == {"c1"}


def test_an_empty_catalogue_says_so():
    theatre = build_theatre([_record("a", "Alpha")], {})
    assert theatre["count"] == 0
    assert theatre["lanes"] == []
    assert theatre["overlap_rule"] == OVERLAP_RULE


def test_every_live_segment_in_the_store_appears_once(client):
    store = client.app.state.systems_store
    expected = {
        segment["id"]
        for record in store.list()
        for segment in (store.compendium_object(record["id"]) or {}).get(
            "pol_segments", []
        )
        if not segment.get("archived")
    }
    served = _served(client)
    seen = [s["id"] for s in _segments(served).values()]
    assert served["count"] == len(expected) == len(seen) > 0
    assert set(seen) == expected


def test_the_dogfighting_triad_shares_a_period_with_its_counterpart(client):
    """The one co-occurrence the sources describe, found by the rule alone.

    CSIS describes the Shiyan-24C triad manoeuvring against SJ-6-05A in March
    2025. Nothing links the two in the data except their dates, so this is the
    rule reproducing a known event rather than a test of a fixture.
    """
    segments = list(_segments(_served(client)).values())
    by_subject = {s["subject"]: s for s in segments}
    triad = [s for s in segments if s["subject"].startswith("SHIYAN 24C")]
    assert len(triad) == 3
    for segment in triad:
        assert by_subject["SJ-6-05A"]["id"] in segment["shared_period"]


def test_a_finished_capture_does_not_share_a_period_with_the_present(client):
    """SJ-21's 2022 capture has no recorded end. It must not overlap 2025."""
    segments = list(_segments(_served(client)).values())
    docking = next(
        s for s in segments if s["subject"] == "SJ-21" and s["mode"] == "rpo_docking"
    )
    later = {s["id"] for s in segments if s["extent"]["from"] >= "2023"}
    assert not later & set(docking["shared_period"])


def test_a_counterpart_outside_the_catalogue_is_labelled_as_such(client):
    segments = list(_segments(_served(client)).values())
    outside = [
        s for s in segments if s["counterpart"] and not s["counterpart"]["in_catalogue"]
    ]
    assert outside, "the seeded store names counterparts outside the catalogue"
    assert all(s["counterpart"]["id"].startswith("target:") for s in outside)


def test_the_theatre_carries_no_rank(client):
    served = _served(client)
    keys = set(served)
    for segment in _segments(served).values():
        keys |= set(segment)
    assert keys & FORBIDDEN_FIELDS == set()


def _theatre_script() -> str:
    """The theatre's script, not its stylesheet, which carries the same banner."""
    start = INDEX_HTML.index("const STAGE_VIEWS")
    return INDEX_HTML[start : INDEX_HTML.index("------ dossier", start)]


def test_the_theatre_colours_by_provenance_never_by_the_series_palette():
    """The series palette identifies a satellite in a chart. A band painted
    from it would be read as an object identity."""
    script = _theatre_script()
    assert "provenanceClass(segment.claim)" in script
    assert "SERIES_COLOURS" not in script
    assert "colourFor" not in script


def test_the_overlap_rule_is_served_not_restated():
    assert OVERLAP_RULE not in INDEX_HTML
    assert "theatreBody.overlap_rule" in INDEX_HTML


def test_the_theatre_never_calls_a_missing_end_ongoing():
    script = _theatre_script()
    assert "ongoing" not in script.lower()
    assert "no end recorded" in script


def test_the_stage_offers_both_views_and_every_band_is_a_button():
    assert re.findall(r'class="vs" data-view="([a-z]+)"', INDEX_HTML) == [
        "space",
        "time",
    ]
    assert '<button type="button" class="${classes.join(" ")}" data-seg=' in INDEX_HTML
