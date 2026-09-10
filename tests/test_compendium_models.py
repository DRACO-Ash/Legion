"""The provenance rules, enforced rather than trusted.

These are the tests that make the house FACT / INFERENCE / SPECULATION rule a
schema instead of a convention. If any of them starts passing for the wrong
reason, an unsourced claim can reach an analyst looking exactly like a
sourced one, which is the failure this whole layer exists to prevent.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.compendium_models import (
    Capability,
    Claim,
    FamilyAssessment,
    PatternOfLifeSegment,
    Relationship,
    Tactic,
    Target,
)

from .conftest import make_claim


def _claim(**overrides) -> Claim:
    return Claim(**make_claim(**overrides))


# --- the two rejection rules ------------------------------------------------


def test_a_fact_without_a_citation_is_rejected() -> None:
    """A fact with no source is a contradiction, not a lesser claim."""
    with pytest.raises(ValidationError, match="must carry a source_citation"):
        _claim(source_citation=None)


def test_a_fact_sourced_only_to_tbc_is_rejected() -> None:
    """ "Marked FACT, sourced to nothing yet" is the exact shape of the error
    this layer exists to make impossible."""
    with pytest.raises(ValidationError, match="cannot have source_class"):
        _claim(source_class="tbc", owner="Ash")


def test_a_tbc_without_an_owner_is_rejected() -> None:
    """An unverifiable claim has to name who is to verify it. The prior
    research pass returned almost nothing and said so honestly; this is that
    honesty as a validator."""
    with pytest.raises(ValidationError, match="must name an owner"):
        _claim(marker="INFERENCE", confidence="low", source_class="tbc", owner=None)


def test_a_tbc_with_an_owner_is_accepted() -> None:
    claim = _claim(
        marker="INFERENCE",
        confidence="low",
        source_class="tbc",
        source_citation=None,
        owner="Ash, cross-check against UDL",
    )
    assert claim.owner == "Ash, cross-check against UDL"


def test_whitespace_does_not_satisfy_the_owner_rule() -> None:
    """A space is not a name. Without this, the rule is trivially defeated."""
    with pytest.raises(ValidationError, match="must name an owner"):
        _claim(marker="SPECULATION", confidence="low", source_class="tbc", owner="   ")


def test_every_claim_must_name_who_asserted_it() -> None:
    """Governance is the editorial layer, and this app has no login auth, so
    this field is the whole of it."""
    payload = make_claim()
    del payload["asserted_by"]
    with pytest.raises(ValidationError):
        Claim(**payload)


def test_speculation_is_allowed_and_keeps_its_marker() -> None:
    """Speculation is a legitimate epistemic state. It must be storable, and
    it must not be quietly promoted."""
    claim = _claim(marker="SPECULATION", confidence="low")
    assert claim.marker == "SPECULATION"


# --- pattern-of-life --------------------------------------------------------


@pytest.mark.parametrize(
    "mode",
    ["rpo_inspection", "rpo_shadowing", "rpo_corkscrew", "rpo_docking", "pursuit"],
)
def test_a_proximity_mode_must_name_its_counterpart(mode: str) -> None:
    """An RPO is always with something. Without the counterpart the segment
    cannot drive a relative-motion view and reads as a solo behaviour."""
    with pytest.raises(ValidationError, match="must name the counterpart"):
        PatternOfLifeSegment(
            object_id="obj-1", mode=mode, start_epoch="2024-05-01", claim=_claim()
        )


def test_a_solo_mode_needs_no_counterpart() -> None:
    segment = PatternOfLifeSegment(
        object_id="obj-1",
        mode="longitudinal_drift",
        start_epoch="2024-05-01",
        claim=_claim(),
    )
    assert segment.related_object_id is None


def test_instantaneous_modes_are_flagged_as_nodes_not_bands() -> None:
    """A separation is a point in time. Drawing it as a band would invent a
    duration the data does not have."""
    node = PatternOfLifeSegment(
        object_id="obj-1",
        mode="separation_event",
        start_epoch="2024-05-01",
        claim=_claim(),
    )
    span = PatternOfLifeSegment(
        object_id="obj-1",
        mode="station_keeping",
        start_epoch="2024-05-01",
        claim=_claim(),
    )
    assert node.is_instantaneous is True
    assert span.is_instantaneous is False


def test_observability_is_separate_from_confidence_and_defaults_to_unknown() -> None:
    """How sure we are that an assessment is right, and how well we could see
    the thing, are different questions. A segment from a sparse track and one
    from a dense track must not be indistinguishable."""
    segment = PatternOfLifeSegment(
        object_id="obj-1",
        mode="station_keeping",
        start_epoch="2024-05-01",
        claim=_claim(confidence="high"),
    )
    assert segment.observability == "unknown"
    assert segment.claim.confidence == "high"


# --- the entities that carry a claim ---------------------------------------


def test_every_ontology_entity_carries_provenance() -> None:
    """The checklist question: can any domain claim reach an analyst without a
    source? Constructing each entity without its claim must fail."""
    unsourced = [
        (Capability, {"kind": "robotic_arm", "label": "Robotic arm"}),
        (Target, {"common_name": "USA 314"}),
        (
            Relationship,
            {
                "kind": "coplanar_with",
                "from_id": "a",
                "from_type": "object",
                "to_id": "b",
                "to_type": "target",
            },
        ),
    ]
    for model, payload in unsourced:
        with pytest.raises(ValidationError):
            model(**payload)


def test_a_tactic_carries_the_weapon_axes_and_they_are_optional() -> None:
    """The axes are what make cross-system comparison answerable. An enabling
    tactic is not a weapon, so it must not be forced to fill them."""
    tactic = Tactic(
        slug="co-planar-shadowing",
        name="Co-planar shadowing",
        tactic_class="enabling",
        description_claim=_claim(),
        observable="Sustained near-zero plane separation with an allied asset.",
    )
    assert tactic.axes.origin_destination is None
    assert tactic.axes.requires_sda_to_employ is None

    kinetic = Tactic(
        slug="noncooperative-capture",
        name="Noncooperative capture",
        tactic_class="kinetic",
        description_claim=_claim(),
        axes={
            "origin_destination": "space_to_space",
            "permanence": "permanent",
            "scale_of_effect": "limited_regional",
            "attributability": "trackable_orbit",
            "requires_space_launch": True,
            "requires_sda_to_employ": True,
        },
    )
    assert kinetic.axes.permanence == "permanent"


def test_a_family_assessment_is_unvalidated_until_a_role_holder_signs_it() -> None:
    """An assessment reconstructed from open sources is not authoritative
    because it is written down. The interface reads this flag."""
    assessment = FamilyAssessment(
        family_id="chn-sj", one_line=_claim(), role_summary=_claim()
    )
    assert assessment.validated_by is None
    assert assessment.awaiting_validation is True

    assessment.validated_by = "Ash, JCO SME"
    assert assessment.awaiting_validation is False
