"""The briefing export: house style enforced, and provenance carried.

House style is checked against text built from controlled fixture content,
not from whatever an analyst has typed into the store. The rules bind what
this application writes; they do not license failing a test because somebody
pasted an American spelling into a note.

The provenance rules are checked against the real seeded content, because
that is where they have to hold.
"""

from __future__ import annotations

import re

import pytest

from src.briefing import BULLET, build_briefing
from src.comparison import build_comparison

from .conftest import make_claim


def _subject(label: str, **overrides) -> dict:
    body = {
        "id": f"id-{label}",
        "kind": "object",
        "label": label,
        "attributes": {
            "Nation": {"value": "CN", "absent": None},
            "Regime": {"value": None, "absent": "not recorded"},
        },
        "baseline": {"value": "GEO station-keeping, 0.5 to 1 m/s", "absent": None},
        "capabilities": [
            {
                "kind": "robotic_arm",
                "label": "Robotic arm",
                "marker": "INFERENCE",
                "confidence": "moderate",
                "citation": "A cited source",
            }
        ],
        "behaviour": ["RPO, docking, 2022"],
        "awaiting_validation": True,
    }
    body.update(overrides)
    return body


def _text(*subjects) -> str:
    return build_briefing(build_comparison(list(subjects)))["text"]


# --- house style ------------------------------------------------------------


@pytest.mark.parametrize(
    ("forbidden", "why"),
    [
        ("—", "em-dash"),
        ("--", "double dash"),
        ("– ", "en-dash used as an em-dash"),
    ],
)
def test_the_briefing_uses_no_dash_the_house_style_forbids(forbidden, why) -> None:
    assert forbidden not in _text(_subject("SJ-21")), why


def test_bullets_are_the_house_character() -> None:
    """`-` and `*` bullets are both out. One character, everywhere."""
    text = _text(_subject("SJ-21"))
    assert BULLET in text
    assert re.search(r"^\s*[-*]\s", text, re.MULTILINE) is None


def test_there_are_no_horizontal_rules() -> None:
    text = _text(_subject("SJ-21"))
    assert re.search(r"^\s*([-_*])\1{2,}\s*$", text, re.MULTILINE) is None


def test_a_plus_is_never_used_as_a_conjunction() -> None:
    assert " + " not in _text(_subject("SJ-21"))


def test_it_leads_with_the_point() -> None:
    """The classification banner, then what this briefing is about. An
    analyst pasting it into a document should not have to hunt for either."""
    lines = [line for line in _text(_subject("SJ-21")).splitlines() if line.strip()]
    assert lines[0].startswith("UNCLASSIFIED")
    assert lines[1].startswith("Briefing: SJ-21")


def test_a_comparison_names_every_subject_in_its_headline() -> None:
    lines = [
        line
        for line in _text(_subject("A"), _subject("B")).splitlines()
        if line.strip()
    ]
    assert lines[1] == "Comparison briefing: A, B."


# --- provenance -------------------------------------------------------------


def test_every_statement_carries_its_marker_and_its_source() -> None:
    """The rule that matters most. A briefing that drops the marker turns an
    inference into a fact on its way to somebody else's desk."""
    text = _text(_subject("SJ-21"))
    assert "[INFERENCE, moderate. A cited source]" in text


def test_an_unvalidated_assessment_says_so_at_the_top_and_beside_the_subject() -> None:
    text = _text(_subject("SJ-21"))
    assert "1 of 1 assessments in this briefing are not validated" in text
    assert "Not validated." in text


def test_a_validated_assessment_carries_no_caveat() -> None:
    text = _text(_subject("SJ-21", awaiting_validation=False))
    assert "not validated" not in text.lower()


def test_an_absent_value_says_why_it_is_absent() -> None:
    """In a briefing a blank reads as a finding. It almost never is."""
    assert f"{BULLET} Regime: (not recorded)" in _text(_subject("SJ-21"))


def test_a_claim_with_no_statement_produces_no_bullet() -> None:
    from src.briefing import _statement

    assert _statement(None) is None
    assert _statement({"statement": "   "}) is None
    assert _statement(make_claim()) is not None


# --- the real content -------------------------------------------------------


def test_a_briefing_on_a_real_object_carries_the_banner_and_the_sources(
    client,
) -> None:
    systems = client.get("/api/systems").json()["systems"]
    target = next(s for s in systems if s["catalogue_name"] == "SJ-21")

    body = client.get("/api/briefing", params={"ids": [target["id"]]}).json()

    assert body["text"].startswith("UNCLASSIFIED")
    assert "CSIS Space Threat Assessment 2025" in body["text"]
    assert body["unvalidated"] == 1


def test_a_briefing_needs_at_least_one_subject(client) -> None:
    assert client.get("/api/briefing").status_code == 400
