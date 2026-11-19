"""The dossier: one object, every section labelled by what is behind it.

The dossier's whole value is that a tab says what it holds before it is
opened, so the one thing it must never do is disagree with the panel behind
the tab. Each count here is therefore checked against the endpoint that
renders that section, not against a number written into the test.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import src.app as app_module
from src.app import build_app
from src.attention import CATEGORY_ORDER, OPEN_BEHAVIOUR, SECTION_FOR, UNSIGNED
from src.dossier import (
    ASSESSMENT,
    BEHAVIOUR,
    NO_ASSESSMENT,
    SECTION_ORDER,
    SIGNED,
    build_dossier,
)
from src.ranking_policy import FORBIDDEN_FIELDS

from .conftest import make_seed_record, make_settings
from .test_ui_contracts import INDEX_HTML


def _system(client, name: str) -> dict:
    systems = client.get("/api/systems").json()["systems"]
    return next(record for record in systems if record["catalogue_name"] == name)


def _dossier(client, record_id: str) -> dict:
    response = client.get(f"/api/objects/{record_id}/dossier")
    assert response.status_code == 200, response.json()
    return response.json()


def _sections(dossier: dict) -> dict:
    return {section["key"]: section for section in dossier["sections"]}


def test_every_section_is_present_in_the_declared_order(client):
    dossier = _dossier(client, _system(client, "SJ-21")["id"])
    assert [section["key"] for section in dossier["sections"]] == list(SECTION_ORDER)
    assert all(section["summary"].strip() for section in dossier["sections"])


@pytest.fixture
def unthrottled(fake_udl, tmp_path, monkeypatch):
    """A client whose global limiter will not trip on a whole-catalogue sweep.

    Four reads for each of 56 objects is past the 120 a minute the process
    allows, and a 429 halfway through reads as a missing key, not a limit.
    Raised for this app instance only; the shipped constant is untouched.
    """
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    monkeypatch.setattr(app_module, "GLOBAL_LIMIT_PER_MINUTE", 10_000)
    with TestClient(build_app(settings=make_settings(), udl_client=fake_udl)) as c:
        yield c


def test_each_count_agrees_with_the_panel_behind_its_tab(unthrottled):
    """The tab and the pane are two reads of one store, and must say the same.

    Checked across every object in the catalogue rather than one, because a
    count that is right for the object a test happens to pick proves little.
    """
    client = unthrottled
    for record in client.get("/api/systems").json()["systems"]:
        sections = _sections(_dossier(client, record["id"]))
        claims = client.get(f"/api/objects/{record['id']}/claims").json()
        timeline = client.get(f"/api/objects/{record['id']}/timeline").json()
        graph = client.get(f"/api/graph/{record['id']}").json()

        name = record["catalogue_name"]
        assert sections["provenance"]["count"] == claims["count"], name
        assert sections["behaviour"]["count"] == timeline["count"], name
        assert sections["connections"]["count"] == len(graph["edges"]), name


def test_outstanding_is_the_queue_narrowed_to_this_object(client):
    """Read from the same builder, so the dossier and the queue cannot differ."""
    record = _system(client, "SJ-21")
    dossier = _dossier(client, record["id"])
    queue = client.get("/api/attention", params={"limit": 500}).json()
    mine = {record["id"], f"family:{record['family_id']}"}

    expected = [entry for entry in queue["entries"] if entry["subject_id"] in mine]
    assert dossier["outstanding"] == expected
    assert dossier["outstanding_count"] == len(expected) > 0


def test_every_queue_entry_names_a_real_dossier_section(client):
    """The interface opens the tab the server names, so it must be one."""
    queue = client.get("/api/attention", params={"limit": 500}).json()
    assert queue["entries"], "an empty queue proves nothing here"
    assert {entry["section"] for entry in queue["entries"]} <= set(SECTION_ORDER)
    assert set(SECTION_FOR) == set(CATEGORY_ORDER)
    assert SECTION_FOR[OPEN_BEHAVIOUR] == BEHAVIOUR
    assert SECTION_FOR[UNSIGNED] == ASSESSMENT


def test_an_open_behaviour_flags_its_own_tab(client):
    record = _system(client, "SJ-21")
    dossier = _dossier(client, record["id"])
    open_sections = {entry["section"] for entry in dossier["outstanding"]}
    assert BEHAVIOUR in open_sections
    assert "no recorded end" in _sections(dossier)["behaviour"]["summary"]


def test_an_assessment_with_nothing_to_verify_is_complete_not_empty():
    """Its count is zero and it is not empty. The interface dimmed it as empty
    until the server said which, so emptiness is served rather than inferred."""
    dossier = build_dossier(
        record=make_seed_record(id="x"),
        layer={},
        assessment={"family_id": "f", "validated_by": "A. Analyst"},
        edge_count=0,
        outstanding=[],
    )
    assessment = _sections(dossier)["assessment"]
    assert dossier["assessment_state"] == SIGNED
    assert assessment["count"] == 0
    assert assessment["empty"] is False


def test_no_assessment_at_all_reads_as_empty():
    dossier = build_dossier(
        record=make_seed_record(id="x"),
        layer={},
        assessment=None,
        edge_count=0,
        outstanding=[],
    )
    assert dossier["assessment_state"] == NO_ASSESSMENT
    assert _sections(dossier)["assessment"]["empty"] is True
    assert "No family assessment" in _sections(dossier)["assessment"]["summary"]


def test_an_object_with_no_catalogue_number_says_it_cannot_be_charted():
    dossier = build_dossier(
        record=make_seed_record(id="x", norad_id=None),
        layer={},
        assessment=None,
        edge_count=0,
        outstanding=[],
    )
    assert dossier["chartable"] is False
    assert "cannot be charted" in dossier["chart_note"]


def test_archived_segments_and_claims_are_not_counted():
    """Archive-not-delete keeps them in the store. They are not what is held."""
    layer = {
        "claims": [{"statement": "a"}, {"statement": "b", "archived": True}],
        "pol_segments": [{"mode": "drift", "archived": True}],
    }
    dossier = build_dossier(
        record=make_seed_record(id="x"),
        layer=layer,
        assessment=None,
        edge_count=0,
        outstanding=[],
    )
    sections = _sections(dossier)
    assert sections["provenance"]["count"] == 1
    assert sections["behaviour"]["count"] == 0
    assert sections["behaviour"]["empty"] is True


def test_the_dossier_carries_no_rank_of_its_own(client):
    """It counts what is held. It does not order or weigh it."""
    dossier = _dossier(client, _system(client, "SJ-21")["id"])
    keys = set(dossier) | {key for s in dossier["sections"] for key in s}
    assert keys & FORBIDDEN_FIELDS == set()


def test_an_unknown_object_is_a_404(client):
    assert client.get("/api/objects/no-such-object/dossier").status_code == 404


def test_the_interface_offers_exactly_the_served_sections():
    """A tab with no section behind it, or a section with no tab, is a defect."""
    tabs = re.findall(r'class="tab" data-tab="([a-z]+)"', INDEX_HTML)
    panes = re.findall(r'class="tab-pane" id="pane-([a-z]+)"', INDEX_HTML)
    assert tabs == list(SECTION_ORDER)
    assert panes == list(SECTION_ORDER)


def test_the_interface_opens_the_section_the_server_names():
    """The category-to-tab mapping lives in src/attention.py and nowhere else.

    A retyped copy in the interface would drift the first time a category was
    reworded, so the script must not contain any category label at all.
    """
    for category in CATEGORY_ORDER:
        assert category not in INDEX_HTML, f"the interface keeps a copy of {category!r}"
    assert "showTab(entry.section)" in INDEX_HTML


def test_a_dossier_can_be_linked_and_the_back_button_works():
    assert 'addEventListener("popstate"' in INDEX_HTML
    assert "history.pushState" in INDEX_HTML
    assert "await applyAddress();" in INDEX_HTML
