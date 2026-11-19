"""Triage: the queue walked one item at a time, to each item's own control.

Triage decides an item is resolved when the rebuilt queue no longer carries
its key. That is only sound if three things hold, and each is a test here:
every key is unique, every target names something real that is still open,
and fixing one item removes exactly that item's key and no other. A key that
two entries shared, or a fix that cleared a neighbour, would make triage
report work as done that nobody did.
"""

from __future__ import annotations

import re

from src.attention import OPEN_BEHAVIOUR, UNSIGNED, UNVERIFIED
from src.compendium_models import INSTANTANEOUS_MODES
from src.ranking_policy import FORBIDDEN_FIELDS

from .test_ui_contracts import INDEX_HTML


def _queue(client) -> dict:
    response = client.get("/api/attention", params={"limit": 500})
    assert response.status_code == 200, response.json()
    return response.json()


def _keys(client) -> set[str]:
    return {entry["key"] for entry in _queue(client)["entries"]}


def _first(client, category: str) -> dict:
    return next(e for e in _queue(client)["entries"] if e["category"] == category)


def _assessment(client, family_id: str) -> dict:
    return client.app.state.systems_store.get_compendium(
        "family_assessments", family_id
    )


def test_every_key_is_unique_and_stable(client):
    first = [entry["key"] for entry in _queue(client)["entries"]]
    assert first, "an empty queue proves nothing"
    assert len(first) == len(set(first))
    assert first == [entry["key"] for entry in _queue(client)["entries"]]


def test_every_target_names_something_real_and_still_open(client):
    """A target that points at nothing would open a control that is not there."""
    store = client.app.state.systems_store
    kinds = set()
    for entry in _queue(client)["entries"]:
        target = entry["target"]
        kinds.add(target["kind"])
        if target["kind"] == "claim":
            claim = _assessment(client, target["family_id"])[target["field"]]
            assert claim["source_class"] == "tbc", entry["key"]
        elif target["kind"] == "signoff":
            assert not _assessment(client, target["family_id"]).get("validated_by")
        elif target["kind"] == "segment":
            layer = store.compendium_object(target["system_id"])
            segment = next(
                s for s in layer["pol_segments"] if s["id"] == target["segment_id"]
            )
            assert not segment.get("end_epoch")
            assert segment["mode"] not in INSTANTANEOUS_MODES
        else:
            assert target["kind"] == "record"
            assert not store.get(target["system_id"]).get(target["field"])
    assert {"claim", "signoff", "segment"} <= kinds


def test_ending_a_segment_removes_exactly_its_key(client):
    entry = _first(client, OPEN_BEHAVIOUR)
    before = _keys(client)
    target = entry["target"]
    response = client.patch(
        f"/api/objects/{target['system_id']}/segments/{target['segment_id']}",
        json={"end_epoch": "2025-06"},
    )
    assert response.status_code == 200, response.json()
    assert before - _keys(client) == {entry["key"]}
    assert _keys(client) - before == set()


def test_signing_off_removes_exactly_its_key(client):
    entry = _first(client, UNSIGNED)
    before = _keys(client)
    response = client.post(
        f"/api/families/{entry['target']['family_id']}/assessment/validation",
        json={"validated_by": "A. Analyst"},
    )
    assert response.status_code == 200, response.json()
    assert before - _keys(client) == {entry["key"]}


def test_verifying_a_claim_removes_exactly_its_key(client):
    """A family can carry two unverified fields. Verifying one must leave the
    other queued, which is what keying on the field rather than the family
    buys: keyed on the family, triage would report both done."""
    entry = _first(client, UNVERIFIED)
    target = entry["target"]
    claim = dict(_assessment(client, target["family_id"])[target["field"]])
    claim.update(
        source_class="think_tank",
        source_citation="CSIS Space Threat Assessment 2025",
        asserted_by="A. Analyst",
    )
    before = _keys(client)
    response = client.patch(
        f"/api/families/{target['family_id']}/assessment",
        json={target["field"]: claim},
    )
    assert response.status_code == 200, response.json()
    assert before - _keys(client) == {entry["key"]}


def test_a_target_carries_no_rank(client):
    keys = set()
    for entry in _queue(client)["entries"]:
        keys |= set(entry) | set(entry["target"])
    assert keys & FORBIDDEN_FIELDS == set()


def _triage_script() -> str:
    start = INDEX_HTML.index("const TRIAGE_WAIT_MS")
    return INDEX_HTML[start : INDEX_HTML.index("------ theatre", start)]


def test_there_is_a_finder_for_every_kind_of_target(client):
    finders = set(
        re.findall(
            r"^  ([a-z]+): ", _triage_script().split("TRIAGE_FINDERS")[1], re.MULTILINE
        )
    )
    served = {entry["target"]["kind"] for entry in _queue(client)["entries"]}
    assert served | {"record"} <= finders


def test_triage_never_writes_anything_itself():
    """It routes through the dossier's forms. A write of its own would be a
    second copy of the anti-shrink merge, and would also make "resolved"
    something triage could assert rather than something the store reports."""
    script = _triage_script()
    assert "method:" not in script
    assert "localStorage" not in script


def test_resolution_is_read_from_the_rebuilt_queue():
    script = _triage_script()
    assert "live.has(item.key)" in script
    assert "await triageCheck();" in INDEX_HTML.split("async function loadAttention")[1]


def test_triage_spends_nothing_from_the_udl_call_budget():
    """Triage selects object after object. Each selection used to plot that
    object's movement, a live UDL call through the strict limiter, which is
    the only control on the UDL budget. Found by driving triage quickly in a
    browser, where the global limiter refused the page within a minute."""
    assert "if(!triage) void showObjectChart(record);" in INDEX_HTML
    assert "if(!triage) void showFamilyChart();" in INDEX_HTML
    assert "pauseChartsForTriage();" in _triage_script()


def test_a_missing_control_names_the_real_cause():
    """A rate-limited request and an already-fixed item look identical unless
    the section's own error is read. The message must not guess."""
    script = _triage_script()
    assert 'paneMsg?.classList.contains("error")' in script
