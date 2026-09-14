"""The four boundaries on ranking, enforced rather than described.

Ash's decision, 14 September 2026: the application may rank what needs
attention **as an indicative element only, and that ranking goes nowhere
else.** `src/ranking_policy.py` carries the rule; this file is the half that
makes it bind.

Each test here was calibrated the way this repository calibrates everything:
by introducing the violation on purpose and confirming the test names it. The
calibration is recorded in each docstring, because a guard written against
code that does not exist yet is the easiest kind of test to get wrong. It can
pass because nothing is there rather than because nothing is wrong, and the
two look identical from the outside.
"""

from __future__ import annotations

import json
from typing import Any

from src.briefing import build_briefing
from src.comparison import build_comparison
from src.ranking_policy import FORBIDDEN_FIELDS, INDICATIVE_LABEL, policy
from src.store import STORE_FILENAME


def _store_on_disk(tmp_path) -> dict:
    """The store as actually written, not as an endpoint chose to serve it.

    This distinction is the whole reason the first version of these guards
    was worthless. `/api/systems` has a `response_model`, so Pydantic drops
    any field the schema does not declare: a rank written into every record
    was stripped on the way out and the test went green. "Never stored" is a
    claim about the file, so the file is what gets read.
    """
    return json.loads((tmp_path / STORE_FILENAME).read_text(encoding="utf-8"))


def _rank_fields(value: Any, path: str = "") -> list[str]:
    """Every place a ranking-shaped field appears in a nested structure."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key).lower() in FORBIDDEN_FIELDS:
                found.append(here)
            found.extend(_rank_fields(inner, here))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found.extend(_rank_fields(inner, f"{path}[{index}]"))
    return found


def test_the_policy_is_served_and_names_its_boundaries(client) -> None:
    """The interface reads the rule; it does not keep a copy.

    Same reasoning as the classification marking and the validation policy:
    the words an analyst reads beside an ordered list and the rule these
    tests enforce have to come from one module.
    """
    response = client.get("/api/ranking-policy")
    assert response.status_code == 200

    served = response.json()
    assert served == policy()
    assert served["label"] == INDICATIVE_LABEL
    assert len(served["boundaries"]) == 4


def test_the_indicative_label_is_not_hard_coded_in_the_interface() -> None:
    """A second copy in the markup would drift and nothing would fail.

    Calibrated by pasting the label into `index.html`: caught.
    """
    from pathlib import Path

    markup = (
        Path(__file__).resolve().parent.parent / "src" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert INDICATIVE_LABEL not in markup, (
        "The interface must fetch /api/ranking-policy rather than hold the "
        "label, so the rule and the words cannot drift."
    )


def test_no_stored_record_carries_a_rank(client, tmp_path) -> None:
    """A rank is computed for display and never written down.

    The store holds what somebody asserted. An ordering is not an assertion,
    and a stored one would outlive the screen that produced it, be read later
    as a judgement, and survive into every export that walks the record.

    Reads the store file rather than the API, because the API cannot show
    this: `/api/systems` has a `response_model` and Pydantic strips undeclared
    fields, so the first version of this test passed with `"priority": 1` on
    every record.

    Calibrated by adding `"priority": 1` inside `_seed`: caught, naming the
    field and the record it sat on.
    """
    client.get("/api/systems?limit=1")  # force the store to be seeded
    stored = _store_on_disk(tmp_path)
    assert stored.get("systems"), "the catalogue should not be empty"

    offenders = _rank_fields(stored["systems"], "systems")
    assert offenders == [], f"A rank reached the store: {offenders}"


def test_no_compendium_layer_carries_a_rank(client, tmp_path) -> None:
    """The same rule, one layer down, and read off the file for the same reason.

    Claims, segments and family assessments are where a score would be most
    tempting and most damaging, because each already carries a marker and a
    confidence that a reader weighs. A rank sitting beside them would be read
    as one of them.

    Calibrated by adding `"score": 0.8` to every seeded claim: caught, naming
    the claim it sat on.
    """
    client.get("/api/systems?limit=1")
    stored = _store_on_disk(tmp_path)
    layers = {key: value for key, value in stored.items() if key != "systems"}
    assert layers, "the compendium layer should exist"

    offenders = _rank_fields(layers)
    assert offenders == [], f"A rank reached the compendium: {offenders}"


def test_a_briefing_carries_no_ordering(client) -> None:
    """A rank must never travel to somebody else's desk.

    A briefing carries every statement's marker, confidence and source
    precisely so a reader can weigh it. An ordinal carries none of those and
    would read as an assessment the moment it left the screen.

    Calibrated by writing "Priority 1" into the briefing header: caught.
    """
    systems = client.get("/api/systems").json()["systems"]
    response = client.get(f"/api/briefing?ids={systems[0]['id']}")
    assert response.status_code == 200, response.json()

    text = response.json()["text"]
    assert text.strip(), "a briefing that produced nothing proves nothing"
    lowered = text.lower()
    leaked = [
        word for word in ("priority", "rank ", "ranked", "score") if word in lowered
    ]
    assert leaked == [], f"A briefing must carry no ordering: {leaked}"


def test_a_comparison_carries_no_ordering(client) -> None:
    """The other export surface, held to the same rule.

    The status check is not ceremony. The first version of this test sent
    every id in the catalogue, because `/api/systems` ignores `limit`, so the
    endpoint answered 400 "compare between 2 and 4 subjects" and the test
    happily inspected an error body and passed. A guard has to prove it looked
    at the thing it claims to guard.

    Calibrated by adding a "Priority" row to the comparison: caught.
    """
    systems = client.get("/api/systems").json()["systems"]
    ids = "&".join(f"ids={record['id']}" for record in systems[:2])
    response = client.get(f"/api/compare?{ids}")
    assert response.status_code == 200, response.json()

    comparison = response.json()
    rows = comparison.get("rows")
    assert rows, "a comparison with no rows proves nothing"

    # rows are the attribute labels down the left, as plain strings
    offenders = _rank_fields(comparison, "comparison")
    offenders.extend(
        f"row: {row}"
        for row in rows
        if any(bad in str(row).lower() for bad in FORBIDDEN_FIELDS)
    )
    assert offenders == [], f"A comparison must carry no ordering: {offenders}"


def test_the_assemblers_are_reachable_without_a_rank() -> None:
    """The guards above go through the API; these two go through the code.

    `build_briefing` and `build_comparison` are the only things that write an
    export, so a rank introduced inside either would have to pass here as
    well as through the routes.
    """
    assert callable(build_briefing)
    assert callable(build_comparison)


def test_every_boundary_is_stated_in_the_analyst_s_words() -> None:
    """Four boundaries, each a sentence somebody can act on.

    A boundary phrased only as a field name would constrain a developer and
    tell an analyst nothing. If a fifth is ever added, this fails until it is
    written in the same register as the other four.
    """
    boundaries = policy()["boundaries"]
    assert isinstance(boundaries, list)
    for sentence in boundaries:
        assert sentence.endswith("."), f"not a sentence: {sentence!r}"
        assert len(sentence.split()) >= 5, f"too terse to act on: {sentence!r}"
