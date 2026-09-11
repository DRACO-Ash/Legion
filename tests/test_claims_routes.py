"""The claims API, and the rule that an edit cannot defeat the provenance rules.

The most important test here is not that a claim can be created. It is that a
PATCH cannot strip the citation off a FACT. A rule enforced once at creation
and defeatable for ever afterwards is decorative, and decorative provenance is
worse than none: it looks like a guarantee.
"""

from __future__ import annotations

from .conftest import make_claim

CLAIMS = "/api/objects/{}/claims"


def _first_system_id(client) -> str:
    return client.get("/api/systems").json()["systems"][0]["id"]


def _create(client, system_id: str, **overrides):
    return client.post(CLAIMS.format(system_id), json=make_claim(**overrides))


# --- the legend -------------------------------------------------------------


def test_the_legend_explains_every_marker_and_confidence_level(client) -> None:
    """Served rather than hard-coded in the interface, so the words an analyst
    reads cannot drift from the rules the validators enforce."""
    body = client.get("/api/provenance/legend").json()

    assert [m["value"] for m in body["markers"]] == [
        "FACT",
        "INFERENCE",
        "SPECULATION",
    ]
    assert [c["value"] for c in body["confidence_levels"]] == [
        "high",
        "moderate",
        "low",
    ]
    for entry in body["markers"] + body["confidence_levels"]:
        assert entry["label"] and entry["meaning"]


def test_the_legend_says_which_source_classes_are_public(client) -> None:
    """The classification posture is unclassified and open-source derived, so
    which classes point at published material is part of the explanation."""
    classes = {
        s["value"]: s
        for s in client.get("/api/provenance/legend").json()["source_classes"]
    }

    assert classes["think_tank"]["public"] is True
    assert classes["internal_assessment"]["public"] is False
    assert classes["tbc"]["public"] is False
    assert "public material" in classes["internal_assessment"]["caution"]


# --- reading ----------------------------------------------------------------


def test_a_catalogued_object_starts_with_no_claims(client) -> None:
    body = client.get(CLAIMS.format(_first_system_id(client))).json()
    assert body["count"] == 0
    assert body["claims"] == []


def test_claims_on_an_unknown_system_are_a_404(client) -> None:
    response = client.get(CLAIMS.format("not-a-real-system"))
    assert response.status_code == 404
    assert "No system with that id" in response.json()["detail"]


# --- creating ---------------------------------------------------------------


def test_a_claim_is_created_and_read_back(client) -> None:
    system_id = _first_system_id(client)
    created = _create(client, system_id)
    assert created.status_code == 201

    stored = created.json()
    assert stored["marker"] == "FACT"
    assert stored["asserted_by"] == "seed-loader"

    listed = client.get(CLAIMS.format(system_id)).json()
    assert listed["count"] == 1
    assert listed["claims"][0]["id"] == stored["id"]


def test_an_unsourced_fact_is_refused_at_the_boundary(client) -> None:
    """The store never sees it. The rule runs before anything is written."""
    response = _create(client, _first_system_id(client), source_citation=None)
    assert response.status_code == 422


def test_an_ownerless_tbc_is_refused_at_the_boundary(client) -> None:
    response = _create(
        client,
        _first_system_id(client),
        marker="INFERENCE",
        confidence="low",
        source_class="tbc",
        source_citation=None,
    )
    assert response.status_code == 422


def test_an_internal_assessment_without_a_public_basis_is_refused(client) -> None:
    """The classification decision, enforced on the wire as well as in the
    model: unclassified, publicly available information only."""
    response = _create(
        client,
        _first_system_id(client),
        marker="INFERENCE",
        confidence="moderate",
        source_class="internal_assessment",
        source_citation=None,
    )
    assert response.status_code == 422


# --- editing ----------------------------------------------------------------


def test_an_edit_merges_without_clearing_what_it_did_not_send(client) -> None:
    system_id = _first_system_id(client)
    claim_id = _create(client, system_id).json()["id"]

    merged = client.patch(
        f"{CLAIMS.format(system_id)}/{claim_id}", json={"confidence": "moderate"}
    ).json()

    assert merged["confidence"] == "moderate"
    assert merged["source_citation"] == "CSIS Space Threat Assessment 2025"
    assert merged["marker"] == "FACT"


def test_an_edit_cannot_strip_the_citation_off_a_fact(client) -> None:
    """The test this file exists for.

    Enforcing a rule only at creation leaves it defeatable by one PATCH, and
    the claim would then render as a sourced fact with nothing behind it.
    """
    system_id = _first_system_id(client)
    claim_id = _create(client, system_id).json()["id"]

    response = client.patch(
        f"{CLAIMS.format(system_id)}/{claim_id}", json={"source_citation": None}
    )
    assert response.status_code == 422

    unchanged = client.get(CLAIMS.format(system_id)).json()["claims"][0]
    assert unchanged["source_citation"] == "CSIS Space Threat Assessment 2025"


def test_an_edit_cannot_turn_a_sourced_claim_into_an_ownerless_tbc(client) -> None:
    system_id = _first_system_id(client)
    claim_id = _create(client, system_id, marker="INFERENCE", confidence="low").json()[
        "id"
    ]

    response = client.patch(
        f"{CLAIMS.format(system_id)}/{claim_id}", json={"source_class": "tbc"}
    )
    assert response.status_code == 422


def test_editing_an_unknown_claim_is_a_404(client) -> None:
    system_id = _first_system_id(client)
    response = client.patch(
        f"{CLAIMS.format(system_id)}/no-such-claim", json={"confidence": "low"}
    )
    assert response.status_code == 404
    assert "No claim with that id" in response.json()["detail"]


# --- archiving --------------------------------------------------------------


def test_a_claim_is_archived_rather_than_deleted(client) -> None:
    """A withdrawn assessment stays auditable. An analyst has to be able to
    see that a claim was made and later pulled, not find a silent gap."""
    system_id = _first_system_id(client)
    claim_id = _create(client, system_id).json()["id"]

    assert client.delete(f"{CLAIMS.format(system_id)}/{claim_id}").status_code == 200

    assert client.get(CLAIMS.format(system_id)).json()["count"] == 0
    with_archived = client.get(
        CLAIMS.format(system_id), params={"include_archived": True}
    ).json()
    assert with_archived["count"] == 1
    assert with_archived["claims"][0]["archived"] is True


def test_archiving_survives_a_later_edit_to_another_claim(client) -> None:
    """The archive flag is carried through the merge rather than reset by it."""
    system_id = _first_system_id(client)
    first = _create(client, system_id).json()["id"]
    second = _create(client, system_id, statement="A second claim.").json()["id"]

    client.delete(f"{CLAIMS.format(system_id)}/{first}")
    client.patch(f"{CLAIMS.format(system_id)}/{second}", json={"confidence": "low"})

    live = client.get(CLAIMS.format(system_id)).json()
    assert [c["id"] for c in live["claims"]] == [second]
