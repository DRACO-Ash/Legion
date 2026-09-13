"""Comparison: what an empty cell means, and how many subjects are allowed.

The one rule worth the most here is that a blank cell says why it is blank.
A comparison is a search for differences, so an empty cell is read as a
finding, and "no robotic arm" is a different claim from "nobody has written
down whether it has one".
"""

from __future__ import annotations

import pytest

from src.comparison import (
    MAX_SUBJECTS,
    MIN_SUBJECTS,
    NOT_RECORDED,
    _cell,
    build_comparison,
)


def _subject(label: str, attributes: dict) -> dict:
    return {
        "id": f"id-{label}",
        "kind": "object",
        "label": label,
        "attributes": attributes,
        "baseline": _cell(None, "no assessment written"),
        "capabilities": [],
        "behaviour": [],
    }


@pytest.mark.parametrize("empty", [None, "", []])
def test_an_absent_value_carries_a_reason_rather_than_a_blank(empty) -> None:
    assert _cell(empty) == {"value": None, "absent": NOT_RECORDED}


def test_a_present_value_carries_no_reason() -> None:
    assert _cell("GEO") == {"value": "GEO", "absent": None}


def test_zero_is_a_value_not_an_absence() -> None:
    """A count of zero members is a fact about the family. Treating it as
    missing would hide it behind "not recorded"."""
    assert _cell(0)["value"] == 0


def test_the_rows_are_the_union_of_every_subject_s_attributes() -> None:
    """Objects and families do not share an attribute set. Taking the first
    subject's rows would silently drop whatever the others carry."""
    built = build_comparison(
        [
            _subject("A", {"Nation": _cell("CN"), "Regime": _cell("GEO")}),
            _subject("B", {"Nation": _cell("RU"), "Members": _cell(4)}),
        ]
    )

    assert built["rows"] == ["Nation", "Regime", "Members"]


def test_a_subject_missing_a_row_is_not_dropped_from_it() -> None:
    built = build_comparison(
        [
            _subject("A", {"Regime": _cell("GEO")}),
            _subject("B", {"Nation": _cell("RU")}),
        ]
    )
    subject_b = built["subjects"][1]

    assert "Regime" in built["rows"]
    assert subject_b["attributes"].get("Regime") is None


# --- the API bounds ---------------------------------------------------------


def _ids(client, *names) -> list[str]:
    systems = client.get("/api/systems").json()["systems"]
    by_name = {s["catalogue_name"]: s["id"] for s in systems}
    return [by_name[name] for name in names]


def test_two_subjects_compare(client) -> None:
    body = client.get(
        "/api/compare", params={"ids": _ids(client, "SJ-21", "SJ-25")}
    ).json()

    assert body["count"] == MIN_SUBJECTS
    assert [s["label"] for s in body["subjects"]] == ["SJ-21", "SJ-25"]


def test_one_subject_is_not_a_comparison(client) -> None:
    response = client.get("/api/compare", params={"ids": _ids(client, "SJ-21")})
    assert response.status_code == 400
    assert str(MIN_SUBJECTS) in response.json()["detail"]


def test_more_than_four_is_refused(client) -> None:
    """Past four the columns are too narrow to read, which is a real limit
    rather than an arbitrary one."""
    names = ["SJ-17", "SJ-21", "SJ-23", "SJ-25", "SJ-28"]
    response = client.get("/api/compare", params={"ids": _ids(client, *names)})
    assert response.status_code == 400
    assert str(MAX_SUBJECTS) in response.json()["detail"]


def test_an_unknown_subject_is_a_404_that_names_it(client) -> None:
    ids = [*_ids(client, "SJ-21"), "not-a-real-id"]
    response = client.get("/api/compare", params={"ids": ids})

    assert response.status_code == 404
    assert "not-a-real-id" in response.json()["detail"]


def test_a_family_can_be_compared_with_an_object(client) -> None:
    """The mixed case the union-of-rows rule exists for."""
    ids = [*_ids(client, "SJ-21"), "family:chn-tjs"]
    body = client.get("/api/compare", params={"ids": ids}).json()

    assert [s["kind"] for s in body["subjects"]] == ["object", "family"]
    assert "Members" in body["rows"]
    assert "NORAD id" in body["rows"]


def test_an_object_inherits_its_family_s_validation_state(client) -> None:
    """Its baseline and capabilities come from the family assessment, so the
    family's validation state is the object's too. Without this an object
    briefing carried capabilities from an unvalidated assessment in silence."""
    body = client.get(
        "/api/compare", params={"ids": _ids(client, "SJ-21", "SJ-25")}
    ).json()

    assert all(s["awaiting_validation"] for s in body["subjects"])
    assert all(s["capabilities"] for s in body["subjects"])


# --- search -----------------------------------------------------------------


def test_search_finds_an_object_by_its_catalogue_number(client) -> None:
    body = client.get("/api/search", params={"q": "49330"}).json()
    assert "SJ-21" in [row["label"] for row in body["results"]]


def test_search_finds_a_family_and_sorts_it_first(client) -> None:
    """Jumping to a class is the coarser and commoner move."""
    body = client.get("/api/search", params={"q": "shijian"}).json()
    assert body["results"][0]["kind"] == "family"


def test_an_empty_query_still_offers_somewhere_to_go(client) -> None:
    """A palette that opens empty tells an analyst nothing about what exists."""
    body = client.get("/api/search").json()
    assert body["results"]


@pytest.mark.parametrize("query", ["zzzz-not-a-thing", "!!!"])
def test_a_query_matching_nothing_returns_nothing_rather_than_everything(
    client, query
) -> None:
    assert client.get("/api/search", params={"q": query}).json()["results"] == []
