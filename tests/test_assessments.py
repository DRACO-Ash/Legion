"""Family assessments: the content seed's own provenance self-check, as code.

The seed document ends with five checkboxes. Every one of them is a test
here, because a checklist in a markdown file constrains nobody and the whole
point of this layer is that an assessment reconstructed from open sources is
not authoritative merely because it is written down.
"""

from __future__ import annotations

import uuid

import pytest

from src.assessment_seed import SEED_ASSESSMENTS, TBC_OWNER
from src.candidate_systems import CANDIDATE_RECORDS
from src.compendium_models import FamilyAssessment
from src.seed_data import SEED_RECORDS
from src.store import FAMILY_ASSESSMENTS, _add_family_assessments
from src.validation_policy import ENTITLED_TEAM, ENTITLEMENT

CATALOGUE_FAMILIES = {
    str(record["family_id"]) for record in [*SEED_RECORDS, *CANDIDATE_RECORDS]
}


def _store_with(family_ids: list[str]) -> dict:
    systems = {}
    for family_id in family_ids:
        record_id = str(uuid.uuid4())
        systems[record_id] = {"id": record_id, "family_id": family_id}
    return {"schema_version": 5, "systems": systems, "compendium": {}}


def _stored(data: dict) -> dict:
    return data["compendium"][FAMILY_ASSESSMENTS]


def _every_claim(assessment: dict):
    """Every claim in one assessment, wherever it sits."""
    for field in ("one_line", "role_summary", "baseline_claim"):
        if assessment.get(field):
            yield assessment[field]
    yield from assessment.get("what_raises_concern", [])
    for capability in assessment.get("capabilities", []):
        yield capability["claim"]


# --- the seed document's provenance self-check ------------------------------


@pytest.mark.parametrize("assessment", SEED_ASSESSMENTS, ids=lambda a: a["family_id"])
def test_every_assessment_clears_the_provenance_validators(assessment) -> None:
    """The same bar every other claim-carrying record clears."""
    FamilyAssessment.model_validate(assessment)


@pytest.mark.parametrize("assessment", SEED_ASSESSMENTS, ids=lambda a: a["family_id"])
def test_nothing_loads_as_a_bare_fact(assessment) -> None:
    for claim in _every_claim(assessment):
        assert claim["statement"].strip()
        assert claim["marker"] in {"FACT", "INFERENCE", "SPECULATION"}
        assert claim["asserted_by"].strip()


def test_a_single_source_claim_loads_at_moderate_not_high() -> None:
    """The seed's own rule, with one stated exception: CSIS calls the SJ-21
    capture the only confirmed instance in GEO, so it is corroborated in the
    source itself."""
    high = [
        claim["statement"]
        for assessment in SEED_ASSESSMENTS
        for claim in _every_claim(assessment)
        if claim["confidence"] == "high"
    ]
    assert all("SJ-21" in statement for statement in high), high


def test_an_unknown_is_a_tbc_claim_with_a_named_owner() -> None:
    """Five families have no sourced assessment. They say so and name who
    writes one, rather than being absent or quietly filled in. An absent
    family would read as nothing to say, which is a different claim."""
    tbc = [
        claim
        for assessment in SEED_ASSESSMENTS
        for claim in _every_claim(assessment)
        if claim["source_class"] == "tbc"
    ]
    assert tbc
    for claim in tbc:
        assert claim["owner"] == TBC_OWNER
        assert "source_citation" not in claim


def test_no_seeded_assessment_arrives_validated() -> None:
    """Who is entitled to sign one off is still Ash's decision. A seed that
    arrived validated would answer that question by default."""
    assert all(a["validated_by"] is None for a in SEED_ASSESSMENTS)


def test_a_speculation_is_not_quietly_promoted() -> None:
    """The Olymp-2 jamming correlation: CSIS says the causal link is not
    clear, so the co-occurrence is carried and the causation is not."""
    luch = next(a for a in SEED_ASSESSMENTS if a["family_id"] == "rus-luch")
    markers = {claim["marker"] for claim in luch["what_raises_concern"]}
    assert "SPECULATION" in markers


# --- coverage against the real catalogue ------------------------------------


def test_every_catalogue_family_has_an_assessment() -> None:
    """A family with no assessment is a silent gap. The thin ones are present
    and honest instead."""
    assessed = {a["family_id"] for a in SEED_ASSESSMENTS}
    assert CATALOGUE_FAMILIES - assessed == set()


def test_no_assessment_names_a_family_the_catalogue_does_not_hold() -> None:
    """The research writes at line level and the catalogue splits some lines
    across families. An assessment keyed to a line that is not a family would
    never reach an analyst."""
    assessed = {a["family_id"] for a in SEED_ASSESSMENTS}
    assert assessed - CATALOGUE_FAMILIES == set()


def test_a_class_baseline_is_stated_wherever_one_is_published() -> None:
    """Phase 5's bar: a number in the chart is legible as a deviation only
    against a baseline."""
    geo = ["chn-sj", "chn-sy12", "chn-tjs", "rus-luch"]
    for family_id in geo:
        assessment = next(a for a in SEED_ASSESSMENTS if a["family_id"] == family_id)
        assert "0.5 to 1 m/s" in assessment["manoeuvre_baseline"]


# --- the migration ----------------------------------------------------------


def test_the_migration_attaches_one_assessment_per_family() -> None:
    data = _store_with(["chn-sj", "chn-tjs"])
    _add_family_assessments(data, SEED_ASSESSMENTS)

    assert set(_stored(data)) == {"chn-sj", "chn-tjs"}
    assert all(entry["id"] for entry in _stored(data).values())


def test_an_assessment_for_a_family_the_store_lacks_is_skipped() -> None:
    """A hand-pruned catalogue does not accumulate assessments for classes it
    no longer carries."""
    data = _store_with(["chn-sj"])
    _add_family_assessments(data, SEED_ASSESSMENTS)
    assert set(_stored(data)) == {"chn-sj"}


def test_running_the_migration_twice_adds_nothing() -> None:
    """Called directly, not through `_migrate`: the schema guard would make
    the second call a no-op and prove nothing."""
    data = _store_with(["chn-sj"])
    _add_family_assessments(data, SEED_ASSESSMENTS)
    first_id = _stored(data)["chn-sj"]["id"]

    _add_family_assessments(data, SEED_ASSESSMENTS)

    assert len(_stored(data)) == 1
    assert _stored(data)["chn-sj"]["id"] == first_id


def test_an_edited_assessment_is_not_restored_to_its_seeded_text() -> None:
    data = _store_with(["chn-sj"])
    _add_family_assessments(data, SEED_ASSESSMENTS)
    _stored(data)["chn-sj"]["validated_by"] = "Ash"

    _add_family_assessments(data, SEED_ASSESSMENTS)

    assert _stored(data)["chn-sj"]["validated_by"] == "Ash"


# --- the API ----------------------------------------------------------------


FAMILY = "/api/families/chn-sj/assessment"
SIGNER = "Ash, JCO SME"


def test_every_family_is_listed_with_whether_it_is_signed(client) -> None:
    body = client.get("/api/families").json()
    assert body["count"] == len(CATALOGUE_FAMILIES)
    assert all(row["has_assessment"] for row in body["families"])
    assert all(row["awaiting_validation"] for row in body["families"])


def test_an_assessment_is_served_with_its_validation_state(client) -> None:
    body = client.get(FAMILY).json()
    assert body["awaiting_validation"] is True
    assert body["manoeuvre_baseline"].startswith("GEO station-keeping")
    assert len(body["what_raises_concern"]) == 3


def test_an_unknown_family_is_a_404(client) -> None:
    assert client.get("/api/families/not-a-family/assessment").status_code == 404


def test_an_edit_cannot_strip_the_provenance_off_a_statement(client) -> None:
    """Same rule as everywhere else: enforced once at creation and
    defeatable by a PATCH would make it decorative."""
    response = client.patch(
        FAMILY, json={"one_line": {"statement": "Unsourced.", "marker": "FACT"}}
    )
    assert response.status_code == 422


def test_an_edit_merges_without_clearing_what_it_did_not_send(client) -> None:
    merged = client.patch(FAMILY, json={"open_questions": ["One question."]}).json()

    assert merged["open_questions"] == ["One question."]
    assert len(merged["what_raises_concern"]) == 3
    assert merged["awaiting_validation"] is True


def test_signing_an_assessment_off_records_who_did_it(client) -> None:
    """A name, not a boolean. With no application authentication the name is
    the whole of the record."""
    signed = client.post(f"{FAMILY}/validation", json={"validated_by": SIGNER}).json()

    assert signed["awaiting_validation"] is False
    assert signed["validated_by"] == SIGNER
    assert client.get(FAMILY).json()["validated_by"] == SIGNER


def test_a_validation_by_nobody_is_refused(client) -> None:
    """Worse than no validation: it looks like one."""
    assert (
        client.post(f"{FAMILY}/validation", json={"validated_by": "  "}).status_code
        == 422
    )


def test_signing_off_is_a_separate_act_from_editing(client) -> None:
    """Folding the two together would let a routine correction carry a
    validation nobody intended."""
    client.patch(FAMILY, json={"open_questions": ["Still open."]})
    assert client.get(FAMILY).json()["awaiting_validation"] is True


# --- who may sign off -------------------------------------------------------


def test_the_entitlement_is_served_rather_than_hard_coded(client) -> None:
    """The words an analyst reads before signing and the rule recorded
    against the signature must come from one place."""
    body = client.get("/api/families/validation-policy").json()

    assert body["team"] == ENTITLED_TEAM
    assert "may sign off" in body["entitlement"]
    assert body["decided_on"] == "2026-09-14"


def test_the_policy_says_plainly_that_it_is_not_authenticated(client) -> None:
    """Ash's decision widens who may sign. It does not create a way to check
    that the signer is who they say, and the application must not imply it
    has one."""
    body = client.get("/api/families/validation-policy").json()
    assert "not authenticated" in body["caveat"]


def test_a_signature_records_the_entitlement_beside_the_name(client) -> None:
    """A sign-off made today still states the rule it was made under if the
    policy later changes."""
    signed = client.post(f"{FAMILY}/validation", json={"validated_by": SIGNER}).json()

    assert signed["validated_by"] == SIGNER
    assert signed["validated_team"] == ENTITLED_TEAM
    assert signed["validated_entitlement"] == ENTITLEMENT
    assert signed["awaiting_validation"] is False


def test_the_entitlement_survives_a_reread(client) -> None:
    client.post(f"{FAMILY}/validation", json={"validated_by": SIGNER})
    stored = client.get(FAMILY).json()

    assert stored["validated_entitlement"] == ENTITLEMENT
