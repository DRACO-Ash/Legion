"""The segments API: the counterpart rule, on creation and on edit.

The claims tests cover the shared machinery, because both surfaces come from
the same factory. What is tested here is what is specific to a segment: a
proximity mode is meaningless without the object it was conducted against,
and an edit must not be able to remove one.
"""

from __future__ import annotations

from .conftest import make_claim

SEGMENTS = "/api/objects/{}/segments"


def _system_id(client, name: str) -> str:
    systems = client.get("/api/systems").json()["systems"]
    return next(s["id"] for s in systems if s["catalogue_name"] == name)


def _payload(**overrides) -> dict:
    body = {
        "object_id": "placeholder",
        "mode": "station_keeping",
        "start_epoch": "2025-04",
        "claim": make_claim(),
    }
    body.update(overrides)
    return body


# --- the mode vocabulary ----------------------------------------------------


def test_the_served_modes_say_which_are_instants(client) -> None:
    """The interface must not decide for itself that a separation lasts a
    week. A node is a marker, never a band."""
    served = {m["value"]: m for m in client.get("/api/pol/modes").json()["modes"]}

    assert served["separation_event"]["instantaneous"] is True
    assert served["station_keeping"]["instantaneous"] is False
    assert served["rpo_corkscrew"]["needs_counterpart"] is True


# --- creating ---------------------------------------------------------------


def test_a_segment_is_created_and_read_back(client) -> None:
    system_id = _system_id(client, "SJ-21")
    created = client.post(SEGMENTS.format(system_id), json=_payload())
    assert created.status_code == 201
    assert created.json()["mode"] == "station_keeping"


def test_a_proximity_segment_without_a_counterpart_is_refused(client) -> None:
    """An RPO is always with something, and the counterpart is what drives
    the relative-motion view. The rule runs before anything is written."""
    system_id = _system_id(client, "SJ-21")
    response = client.post(
        SEGMENTS.format(system_id), json=_payload(mode="rpo_inspection")
    )
    assert response.status_code == 422
    assert "counterpart" in str(response.json()["detail"])


def test_an_unsourced_segment_claim_is_refused(client) -> None:
    """A segment carries a claim, so the provenance rules reach it too."""
    system_id = _system_id(client, "SJ-21")
    response = client.post(
        SEGMENTS.format(system_id),
        json=_payload(claim=make_claim(source_citation=None)),
    )
    assert response.status_code == 422


# --- editing ----------------------------------------------------------------


def test_an_edit_cannot_strip_the_counterpart_off_a_proximity_segment(client) -> None:
    """The test this file exists for. A rule enforced only at creation is
    defeatable by one PATCH, and the segment would then claim a proximity
    operation against nothing."""
    system_id = _system_id(client, "SJ-21")
    segment_id = client.post(
        SEGMENTS.format(system_id),
        json=_payload(mode="rpo_shadowing", related_object_id="target:usa-314"),
    ).json()["id"]

    response = client.patch(
        f"{SEGMENTS.format(system_id)}/{segment_id}",
        json={"related_object_id": None},
    )
    assert response.status_code == 422


def test_an_edit_cannot_turn_a_solo_mode_into_an_unpartnered_rpo(client) -> None:
    system_id = _system_id(client, "SJ-21")
    segment_id = client.post(SEGMENTS.format(system_id), json=_payload()).json()["id"]

    response = client.patch(
        f"{SEGMENTS.format(system_id)}/{segment_id}", json={"mode": "pursuit"}
    )
    assert response.status_code == 422


def test_an_edit_merges_without_clearing_what_it_did_not_send(client) -> None:
    system_id = _system_id(client, "SJ-21")
    segment_id = client.post(SEGMENTS.format(system_id), json=_payload()).json()["id"]

    merged = client.patch(
        f"{SEGMENTS.format(system_id)}/{segment_id}", json={"observability": "sparse"}
    ).json()

    assert merged["observability"] == "sparse"
    assert merged["start_epoch"] == "2025-04"


# --- the seeded history reaches the wire ------------------------------------


def test_the_seeded_history_is_served_for_a_catalogued_object(client) -> None:
    """The Phase 3 bar is a behavioural history an analyst can see, so the
    seeded segments have to arrive through the real endpoint."""
    system_id = _system_id(client, "COSMOS-2576")
    body = client.get(SEGMENTS.format(system_id)).json()

    shadowing = [s for s in body["segments"] if s["mode"] == "rpo_shadowing"]
    assert shadowing, body
    assert shadowing[0]["start_epoch"] == "2024-05"
    assert shadowing[0]["end_epoch"] == "2025-02"
    assert shadowing[0]["claim"]["source_citation"]


def test_a_seeded_counterpart_we_hold_is_a_real_system_id(client) -> None:
    """SJ-25 and SJ-21 are both catalogued, so the pair links object to
    object rather than object to a name that cannot be navigated."""
    systems = {
        s["catalogue_name"]: s["id"]
        for s in client.get("/api/systems").json()["systems"]
    }
    body = client.get(SEGMENTS.format(systems["SJ-25"])).json()

    partnered = [s for s in body["segments"] if s["related_object_id"]]
    assert partnered
    assert partnered[0]["related_object_id"] == systems["SJ-21"]


# --- the catalogue snapshot -------------------------------------------------


def test_the_reconciliation_is_served_and_the_catalogue_is_clean(client) -> None:
    """An analyst has to be able to see any disagreement without reading the
    repository, and right now there is none to see."""
    body = client.get("/api/satcat/reconciliation").json()
    assert body["checked"] >= 56
    assert body["findings"] == [], body["findings"]


def test_one_catalogue_row_can_be_looked_up(client) -> None:
    body = client.get("/api/satcat/49961").json()
    assert body["name"] == "SHIJIAN 6 05A (SJ-6 05A)"
    assert body["launch_year"] == 2021


def test_a_number_outside_the_snapshot_is_a_404(client) -> None:
    assert client.get("/api/satcat/99999999").status_code == 404
