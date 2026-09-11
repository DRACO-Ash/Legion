"""The compendium layer: provenance-carrying entities for the threat ontology.

Why this module exists, in one sentence: behaviour data alone cannot tell a
weapon from a surveillance asset, and what resolves the ambiguity is
capability plus context plus pattern-of-life (CSIS Space Threat Assessment
2025, "RPOs: Benevolent or Cruel Intentions"). The shipped catalogue holds
static attributes. These models hold the disambiguation layer.

The design principle carried throughout: **the claim is the atom.** Almost
every domain-meaningful field is not a bare value but a `Claim`, a value plus
its provenance. That turns the house FACT / INFERENCE / SPECULATION rule from
a comment into a schema with validators, which is the point. A bare string is
used only for genuinely non-assertive data such as an internal id or a slug.

Two rules are enforced here rather than left to reviewer discipline, because
this project has a documented case of an unverifiable research pass returning
almost nothing and recording that honestly. That honesty is the standard:

  ● A FACT with no source is a contradiction and is rejected.
  ● A TBC with no named owner is rejected, because an unverifiable claim has
    to name who must verify it.

A third rule follows from the classification decision in
`src/classification.py`: this deployment is unclassified and derived from
publicly available information only, so an `internal_assessment` claim must
cite the public material it reasons from. Every other source class names
something published already; an analyst's own assessment does not, and that
is exactly where non-public material could enter unnoticed.

Nothing here replaces `TrackedSystem`. The compendium composes onto it by
`system_id` and the shipped catalogue is untouched.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.classification import DERIVED_NEEDS_CITATION, DERIVED_SOURCE_CLASS

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

ConfidenceMarker = Literal["FACT", "INFERENCE", "SPECULATION"]
ConfidenceLevel = Literal["high", "moderate", "low"]

SourceClass = Literal[
    "official_gov",  # USSF fact sheet, DoD testimony, a state MoD statement
    "peer_reviewed",  # journal or conference paper (AMOS and the like)
    "think_tank",  # CSIS, SWF, CASI
    "commercial_ssa",  # LeoLabs, COMSPOC, ExoAnalytic, Slingshot, s2a
    "press",  # SpaceNews, Breaking Defense, Reuters
    "catalogue",  # Space-Track, Vimpel, GCAT, UDL
    "state_media",  # the originating nation's own media, treat with caution
    "internal_assessment",  # a Bluestaq or JCO analyst assessment
    "tbc",  # not yet sourced. Renders as "TBC, re-verify".
]

SOURCE_CLASS_TBC = "tbc"
MARKER_FACT = "FACT"

# How well the behaviour could actually be seen, which is a different question
# from how sure we are that the assessment is right. A characterisation is only
# as good as the revisit rate: LeoLabs report 7 to 8 passes a day for a LEO
# pair, and a sparse track can miss a manoeuvre entirely. Presenting a dense
# track and a sparse one identically misleads the analyst, which is the same
# principle as the JCO HRR rank gate already in the charts.
Observability = Literal["dense", "moderate", "sparse", "unknown"]

CapabilityKind = Literal[
    "robotic_arm",
    "noncooperative_capture",
    "refuelling",
    "sub_object_release",
    "kinetic_kill_vehicle",
    "sigint_payload",
    "high_delta_v_manoeuvre",
    "coplanar_shadowing",
    "directed_energy",
    "spaceplane_reuse",
    "inspection_rpo",
    "electric_propulsion",
    "chemical_propulsion",
    "other",
]

BehaviourMode = Literal[
    "station_keeping",
    "longitudinal_drift",
    "rpo_inspection",
    "rpo_shadowing",
    "rpo_corkscrew",
    "rpo_docking",
    "pursuit",
    "retirement",
    "separation_event",
    "anomalous_high_dv",
    "quiescent",
    "unknown",
]

# An RPO or a pursuit is always with something, so these modes must name the
# counterpart. That counterpart is also what drives the relative-motion view.
MODES_NEEDING_COUNTERPART = frozenset(
    {"rpo_inspection", "rpo_shadowing", "rpo_corkscrew", "rpo_docking", "pursuit"}
)

# Instantaneous occurrences rather than sustained regimes. They render as a
# marker on the timeline, never as a band.
INSTANTANEOUS_MODES = frozenset({"separation_event", "anomalous_high_dv"})

EventKind = Literal[
    "close_approach",
    "manoeuvre",
    "separation",
    "capture",
    "refuelling",
    "plane_change",
    "graveyard_disposal",
    "breakup",
    "other",
]

RelationshipKind = Literal[
    "belongs_to_family",
    "coplanar_with",
    "shadowed",
    "birthed",
    "approached",
    "captured",
    "refuelled",
    "demonstrated_tactic",
    "threatens",
    "supports",
    "same_series_as",
    "sourced_from",
]

EntityType = Literal["object", "family", "tactic", "target", "event"]

TacticClass = Literal["kinetic", "non_kinetic", "electronic", "cyber", "enabling"]


def now_iso() -> str:
    """Millisecond-precision UTC, matching the store's existing stamp format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_id() -> str:
    return str(uuid.uuid4())


class _Stamped(BaseModel):
    """Identity, timestamps and the archive flag, shared so every entity
    stamps and retires the same way.

    `archived` is here rather than on individual entities because the house
    rule is archive, never delete: a withdrawn assessment has to stay
    auditable, so an analyst can see that a claim was made and later pulled
    rather than finding a silent gap. The store already wrote this field; the
    models now declare it.
    """

    id: str = Field(default_factory=new_id)
    archived: bool = False
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# The atom
# ---------------------------------------------------------------------------


class Claim(_Stamped):
    """One assertion about the world, carrying its own provenance.

    `asserted_by` is required on every claim, not only on a TBC. Governance
    matters even without login authentication: the US Army's milWiki trial
    found that who asserts a thing, and how sure they are, is the editorial
    layer that makes a living reference trustworthy. Legion removed
    authentication as a decision, so this field is the whole of that layer.
    """

    statement: str = Field(min_length=1)
    marker: ConfidenceMarker
    confidence: ConfidenceLevel
    source_class: SourceClass
    asserted_by: str = Field(min_length=1)
    source_citation: str | None = None
    source_url: str | None = None
    as_of: str | None = None
    owner: str | None = None

    @model_validator(mode="after")
    def _provenance_holds(self) -> Claim:
        if self.source_class == SOURCE_CLASS_TBC and not (self.owner or "").strip():
            raise ValueError(
                "A TBC claim must name an owner: an unverifiable claim has to "
                "say who is to verify it."
            )
        if self.marker == MARKER_FACT:
            self._reject_unsourced_fact()
        if self.source_class == DERIVED_SOURCE_CLASS and not self._has_citation():
            raise ValueError(DERIVED_NEEDS_CITATION)
        return self

    def _has_citation(self) -> bool:
        return bool((self.source_citation or "").strip())

    def _reject_unsourced_fact(self) -> None:
        if self.source_class == SOURCE_CLASS_TBC:
            raise ValueError("A FACT cannot have source_class 'tbc'.")
        if not self._has_citation():
            raise ValueError("A FACT must carry a source_citation.")


# ---------------------------------------------------------------------------
# Capability, behaviour and events
# ---------------------------------------------------------------------------


class Capability(_Stamped):
    """Something an object or family can demonstrably, or assessed-to, do.

    This is the field behaviour data cannot supply. "Assessed to have a
    robotic arm" and "confirmed to have towed a satellite" are different
    epistemic states and an analyst has to be able to tell them apart, which
    is why the capability carries a claim rather than being a bare flag.
    """

    kind: CapabilityKind
    label: str = Field(min_length=1)
    claim: Claim


class PatternOfLifeSegment(_Stamped):
    """One behavioural mode between two nodes, the formal SDA PoL model.

    A node is an instantaneous mode-change point; a mode is the sustained
    regime between two nodes (Siew et al., AMOS 2023). The sequence of these,
    sorted by start_epoch, is an object's pattern-of-life timeline.

    These are the *assessed* history. The element-set charts are the *raw*
    observed data from UDL. They are kept distinct on purpose and an
    assessment is never rendered as if it were telemetry.
    """

    object_id: str = Field(min_length=1)
    mode: BehaviourMode
    start_epoch: str = Field(min_length=1)
    claim: Claim
    end_epoch: str | None = None
    related_object_id: str | None = None
    observability: Observability = "unknown"
    observability_note: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _counterpart_present_when_required(self) -> PatternOfLifeSegment:
        needs_counterpart = self.mode in MODES_NEEDING_COUNTERPART
        if needs_counterpart and not (self.related_object_id or "").strip():
            raise ValueError(
                f"Mode '{self.mode}' is a proximity or pursuit regime, so it "
                "must name the counterpart object it was conducted against."
            )
        return self

    @property
    def is_instantaneous(self) -> bool:
        """True for a node rather than a band, so the UI knows how to draw it."""
        return self.mode in INSTANTANEOUS_MODES


class BehaviourEvent(_Stamped):
    """A specific, dateable, citable occurrence, distinct from a sustained mode.

    The open-source assessments are full of exactly these: TJS-10 within 25 km
    of TJS-3, COSMOS-2581 and 2582 100 m apart. Holding them as records rather
    than prose is what lets the graph draw the edge and the timeline place the
    node.
    """

    kind: EventKind
    epoch: str = Field(min_length=1)
    primary_object_id: str = Field(min_length=1)
    claim: Claim
    counterpart_object_id: str | None = None
    counterpart_target_id: str | None = None
    distance_km: float | None = Field(default=None, ge=0)
    delta_v_ms: float | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Targets, tactics and the graph
# ---------------------------------------------------------------------------


class Target(_Stamped):
    """A threatened asset, usually friendly, allied or commercial.

    "Coplanar with USA 314" only means something if USA 314 is modelled, so
    targets are first-class entities and the endpoint of a shadowing edge.
    """

    common_name: str = Field(min_length=1)
    claim: Claim
    norad_id: str | None = None
    operator: str | None = None
    regime: str | None = None
    function: str | None = None


class WeaponAxes(BaseModel):
    """The axes an open-source assessment uses to differentiate weapon types.

    Taken from the CSIS counterspace taxonomy, where each category is
    separated by exactly this set. They are what makes cross-system
    comparison answerable rather than a reading exercise, which is one of the
    driving use cases. Every axis is optional because an enabling tactic is
    not a weapon and should not be forced to fill them in.
    """

    origin_destination: (
        Literal["ground_to_ground", "ground_to_space", "space_to_space"] | None
    ) = None
    permanence: Literal["permanent", "not_permanent", "varies"] | None = None
    scale_of_effect: Literal["limited_regional", "widespread"] | None = None
    attributability: Literal["launch_site", "trackable_orbit", "limited"] | None = None
    requires_space_launch: bool | None = None
    requires_sda_to_employ: bool | None = None


class Tactic(_Stamped):
    """A named, reusable technique: the ATT&CK technique analogue.

    Sitting at the mid level of abstraction is the whole game. Not
    "COSMOS-2519 exists", which is too low to act on, and not "Russia does
    co-orbital RPO", which is too high, but "this class matches a target's
    plane and loiters, and here is the observable that reveals it".
    """

    slug: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tactic_class: TacticClass
    description_claim: Claim
    observable: str | None = None
    axes: WeaponAxes = Field(default_factory=WeaponAxes)


class Relationship(_Stamped):
    """A typed, sourced edge. The ontology made navigable.

    Every edge carries a claim. A coplanar_with edge sourced from a published
    assessment is a different epistemic object from one sourced from a
    social-media graphic, and the analyst has to be able to see which.
    """

    kind: RelationshipKind
    from_id: str = Field(min_length=1)
    from_type: EntityType
    to_id: str = Field(min_length=1)
    to_type: EntityType
    claim: Claim


# ---------------------------------------------------------------------------
# The composed entities
# ---------------------------------------------------------------------------


class CompendiumObject(_Stamped):
    """The compendium layer for one catalogued system.

    Composes onto `TrackedSystem` by `system_id` and never replaces it.
    Relationships are held globally rather than nested here, because an edge
    belongs to neither endpoint.
    """

    system_id: str = Field(min_length=1)
    capabilities: list[Capability] = Field(default_factory=list)
    pol_segments: list[PatternOfLifeSegment] = Field(default_factory=list)
    events: list[BehaviourEvent] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


class FamilyAssessment(_Stamped):
    """The class-level synthesis: what this class is, what it does, what the
    baseline is, and what should raise concern.

    `validated_by` is None until a role-holder signs it off, and the interface
    marks it "awaiting validation" until then. An assessment reconstructed
    from open sources is not authoritative merely because it is written down.
    """

    family_id: str = Field(min_length=1)
    one_line: Claim
    role_summary: Claim
    manoeuvre_baseline: str | None = None
    baseline_claim: Claim | None = None
    what_raises_concern: list[Claim] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    validated_by: str | None = None

    @property
    def awaiting_validation(self) -> bool:
        return not (self.validated_by or "").strip()


class PatternOfLifeSegmentUpdate(BaseModel):
    """A partial segment edit. Every field optional, anti-shrink on merge.

    Like `ClaimUpdate`, deliberately not the full model with optionals: the
    route re-validates the merged result as a whole `PatternOfLifeSegment`,
    so a PATCH cannot turn a solo mode into an RPO without naming the
    counterpart, and cannot strip the counterpart off one that has it.
    """

    mode: BehaviourMode | None = None
    start_epoch: str | None = None
    end_epoch: str | None = None
    claim: Claim | None = None
    related_object_id: str | None = None
    observability: Observability | None = None
    observability_note: str | None = None
    notes: str | None = None


class ClaimUpdate(BaseModel):
    """A partial claim edit. Every field optional, anti-shrink on merge.

    Deliberately not a `Claim` with optional fields: the merged result is
    re-validated as a full `Claim` by the route, so a PATCH cannot strip the
    citation off a FACT or the owner off a TBC. An update that could defeat
    the provenance rules would make them decorative.
    """

    statement: str | None = None
    marker: ConfidenceMarker | None = None
    confidence: ConfidenceLevel | None = None
    source_class: SourceClass | None = None
    asserted_by: str | None = None
    source_citation: str | None = None
    source_url: str | None = None
    as_of: str | None = None
    owner: str | None = None
