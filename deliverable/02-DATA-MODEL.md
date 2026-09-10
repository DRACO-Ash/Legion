# LEGION COMPENDIUM - Data Model Specification

**Scope.** The exact entity shape for the upgrade: fields, types, enums, relationships,
and the migration from the shipped schema. This is the contract Phase 1 implements and
every later phase reads. It is designed to (a) compose cleanly onto the existing
`TrackedSystem` without breaking it, (b) make provenance structural, and (c) express the
ontology as an adjacency structure the JSON store can hold and the client can render.

**Design principle carried throughout:** *the claim is the atom.* Almost every
domain-meaningful field is not a bare value but a `Claim` - a value plus its provenance.
This is what turns the house FACT/INFERENCE/SPECULATION rule from a comment into a
schema. A bare string field is only used for genuinely non-assertive data (an internal
id, a display slug).

---

## 1. The atom: `Claim`

Every assertion about the world is a `Claim`. This is the single most important type in
the upgrade.

```python
ConfidenceMarker = Literal["FACT", "INFERENCE", "SPECULATION"]
ConfidenceLevel = Literal["high", "moderate", "low"]
SourceClass = Literal[
  "official_gov",    # e.g. USSF fact sheet, DoD testimony, state MoD statement
  "peer_reviewed",    # journal / conference paper (AMOS, arXiv-with-review)
  "think_tank",     # CSIS, SWF, CASI
  "commercial_ssa",   # LeoLabs, COMSPOC, ExoAnalytic, Slingshot, s2a, Integrity ISR
  "press",        # SpaceNews, Breaking Defense, Reuters
  "catalogue",      # Space-Track, Vimpel, GCAT, UDL
  "state_media",     # originating-nation state media (treat with stated caution)
  "internal_assessment", # Bluestaq/JCO analyst assessment (carries its own owner)
  "tbc",         # placeholder: not yet sourced. Renders as "TBC, re-verify".
]

class Claim(BaseModel):
  id: str               # uuid
  statement: str            # the assertion, in house style, UK English
  marker: ConfidenceMarker       # FACT / INFERENCE / SPECULATION
  confidence: ConfidenceLevel     # high / moderate / low
  source_class: SourceClass
  source_citation: str | None     # human-readable: author, title, date, org
  source_url: str | None        # if openly linkable; None if not
  as_of: str | None          # ISO date the claim was true/observed
  owner: str | None          # named owner, REQUIRED when source_class == "tbc"
  created_at: str
  updated_at: str
```

**Validation rules (enforce in the model, test them):**
- `source_class == "tbc"` ⇒ `owner` MUST be non-empty. A TBC with no owner is rejected.
 (This is the failed-research-JSON lesson as a validator: an unverifiable claim names
 who must verify it.)
- `marker == "FACT"` ⇒ `source_class` MUST NOT be `"tbc"` and `source_citation` MUST be
 non-empty. A fact with no source is a contradiction and is rejected.
- `marker == "SPECULATION"` is allowed with `confidence == "low"` and any source_class
 including internal_assessment, but the UI must render it visibly as speculation.
- `statement` must be escaped before it reaches markup (extend
 `tests/test_ui_contracts.py`'s existing escaping assertion to cover claim statements).

**Rendering contract (for the UI phases):** a claim is shown as a chip carrying the
marker as **colour + icon + text** (never colour alone), the confidence, the source-class
label, and the date. A TBC claim renders in a distinct "unverified" style and is never
shown as if it were established.

---

## 2. Capability

A thing an object or family can demonstrably (or assessed-to) do. This is the
disambiguation layer from the CSIS "capability + context" framing.

```python
CapabilityKind = Literal[
  "robotic_arm",         # SJ-17/SJ-21 grappling
  "noncooperative_capture",   # SJ-21 Beidou tow (the only confirmed GEO instance)
  "refuelling",         # SJ-25 <-> SJ-21
  "sub_object_release",     # birthing/matryoshka; Shenlong, Nivelir, TJS-3
  "kinetic_kill_vehicle",    # Nivelir KKV ejection
  "sigint_payload",       # Luch/Olymp, TJS SIGINT
  "high_delta_v_manoeuvre",   # TJS-2 at 44 m/s vs 0.5-1 baseline
  "coplanar_shadowing",     # COSMOS-2576/USA-314 pattern
  "directed_energy",       # laser/HPM (mostly ground, assess per case)
  "spaceplane_reuse",      # Shenlong
  "inspection_rpo",       # generic close inspection
  "other",
]

class Capability(BaseModel):
  id: str
  kind: CapabilityKind
  label: str           # short human label, house style
  claim: Claim          # the capability IS a provenance-carrying assertion
  created_at: str
  updated_at: str
```

Rationale: capability is exactly the field that behaviour data alone cannot supply and
that resolves weapon-vs-surveillance ambiguity (CSIS). It must carry provenance because
"assessed to have a robotic arm" and "confirmed to have towed a satellite" are different
epistemic states an analyst must be able to tell apart.

---

## 3. Behavioural modes and the pattern-of-life sequence

From the formal PoL model (Siew et al., AMOS 2023): nodes + behavioural modes.

```python
BehaviourMode = Literal[
  "station_keeping",    # small periodic corrections, GEO baseline 0.5-1 m/s
  "longitudinal_drift",  # walking the belt at a steady deg/day
  "rpo_inspection",    # closing to inspect
  "rpo_shadowing",     # matching plane and loitering (co-planar shadow)
  "rpo_corkscrew",     # walking/corkscrew approach (SY-24C "dogfighting")
  "rpo_docking",      # docking / capture
  "pursuit",        # actively chasing a manoeuvring target
  "retirement",      # raising to graveyard (+~300 km super-sync)
  "separation_event",   # instantaneous: releasing a sub-object (a node, not a span)
  "anomalous_high_dv",   # manoeuvre far outside class baseline
  "quiescent",       # on-orbit, no significant manoeuvre
  "unknown",
]

class PatternOfLifeSegment(BaseModel):
  id: str
  object_id: str         # the CompendiumObject this belongs to
  mode: BehaviourMode
  start_epoch: str        # ISO; the start node
  end_epoch: str | None     # ISO; None if ongoing / current mode
  claim: Claim          # provenance for the mode assessment
  related_object_id: str | None # for RPO/pursuit: the counterpart object
  notes: str | None
  created_at: str
  updated_at: str
```

**Modelling rules:**
- `separation_event` and `anomalous_high_dv` are *nodes* (instantaneous); represent with
 `start_epoch == end_epoch` or `end_epoch = None` and treat as a marker, not a band.
- All other modes are *spans* between two nodes.
- The sequence for an object, sorted by `start_epoch`, is its pattern-of-life timeline.
- `related_object_id` is required for `rpo_*` and `pursuit` modes (an RPO is always with
 something) and drives the relative-motion view.

**Relationship to live UDL charts:** the PoL segments are the *assessed* behavioural
history (provenance-carried, editable). The live element-set charts (existing) are the
*raw* observed data from UDL. Phase 3 overlays the assessed mode-change nodes on the raw
chart so the analyst sees both: what the data shows, and what it has been assessed to
mean. Keep them distinct - never render an assessment as if it were raw telemetry.

---

## 4. Behaviour events (discrete, dateable occurrences)

Distinct from PoL modes (which are sustained regimes), an event is a specific dateable
occurrence an analyst cites: a close approach at a distance, a named manoeuvre, a
separation. These are the nodes in the relationship graph that connect two objects.

```python
EventKind = Literal[
  "close_approach",    # with distance + counterpart
  "manoeuvre",       # with delta-v if known
  "separation",      # birthing a sub-object
  "capture",        # noncooperative capture (SJ-21)
  "refuelling",      # SJ-25/SJ-21
  "plane_change",
  "graveyard_disposal",
  "breakup",        # debris-generating (CSIS debris section)
  "other",
]

class BehaviourEvent(BaseModel):
  id: str
  kind: EventKind
  epoch: str           # ISO date/time of the event
  primary_object_id: str     # the actor
  counterpart_object_id: str | None # the target/other party, if any
  counterpart_target_id: str | None # if the counterpart is a Target not in catalogue
  distance_km: float | None   # for close_approach
  delta_v_ms: float | None    # for manoeuvre, in m/s
  claim: Claim          # provenance
  created_at: str
  updated_at: str
```

Rationale: the CSIS report is full of exactly these ("TJS-10 within 25 km of TJS-3 on
16 May 2024", "COSMOS-2581/2582 100 m apart on 5 March 2025"). Each is a citable event
with a distance, a date, and a source. Holding them as first-class records lets the
analyst build the sequence and lets the graph draw the edge.

---

## 5. Targets (the things being threatened)

An analyst characterising a threat needs the *target* as an entity, because "coplanar
with USA 314" only means something if USA 314 is modelled. Targets are usually friendly/
allied/commercial assets not in the red catalogue.

```python
class Target(BaseModel):
  id: str
  common_name: str        # "USA 314", "Intelsat 10-02", "Thor 7"
  norad_id: str | None
  operator: str | None      # "US Government", "Intelsat", "SES"
  regime: str | None
  function: str | None      # "SDA/GSSAP", "comms/broadcast"
  claim: Claim          # provenance for the characterisation
  created_at: str
  updated_at: str
```

---

## 6. The relationship graph (the ontology made navigable)

The graph is expressed as typed edges. This is the adjacency structure the JSON store
holds and the client renders - no graph database.

```python
RelationshipKind = Literal[
  "belongs_to_family",   # object -> family
  "coplanar_with",     # object -> object|target
  "shadowed",       # object -> object|target
  "birthed",        # object -> object (parent released child)
  "approached",      # object -> object|target (close approach)
  "captured",       # object -> object|target
  "refuelled",       # object -> object
  "demonstrated_tactic",  # object|family -> tactic
  "threatens",       # object|family -> target
  "supports",       # object -> object (e.g. TJS-3 supporting SJ-21 refuel)
  "same_series_as",    # object -> object
  "sourced_from",     # any -> source (provenance edge, optional to render)
]

class Relationship(BaseModel):
  id: str
  kind: RelationshipKind
  from_id: str          # entity id (object/family/tactic/target)
  from_type: Literal["object", "family", "tactic", "target", "event"]
  to_id: str
  to_type: Literal["object", "family", "tactic", "target", "event"]
  claim: Claim          # edges carry provenance too
  created_at: str
  updated_at: str
```

**Graph rules:**
- Every edge carries a `Claim`. A "coplanar_with" edge sourced from a CSIS assessment is
 a different epistemic object from one sourced from a social-media graphic; the analyst
 must be able to see which.
- The client builds the visual graph by indexing edges by `from_id`/`to_id`. For ~49
 objects plus families, targets, and events, this is a few hundred edges at most - 
 trivially renderable client-side.
- Rendering: node colour by entity type (using the CVD-safe palette, NOT the object-
 identity series palette - a separate small categorical set for entity *types*), edge
 style by confidence (solid = FACT, dashed = INFERENCE, dotted = SPECULATION - a
 redundant encoding alongside a text label on hover, never style-alone).

---

## 7. The composed entities

The existing `TrackedSystem` is preserved unchanged. The compendium adds two composed
views that reference it and hang the new structures off it.

```python
class Tactic(BaseModel):
  """A named, reusable technique - the ATT&CK 'technique' analogue.
  e.g. 'solar-exclusion positioning' (TJS-4), 'co-planar shadowing',
  'corkscrew RPO / dogfighting', 'SIGINT loiter near comms sat'."""
  id: str
  slug: str
  name: str           # house style
  tactic_class: Literal["kinetic","non_kinetic","electronic","cyber","enabling"]
  description_claim: Claim
  observable: str | None     # what an analyst watches for to detect it
  created_at: str
  updated_at: str

class CompendiumObject(BaseModel):
  """Extends the tracked system with the compendium layer. Does NOT replace
  TrackedSystem; references it by system_id and composes the new structures."""
  id: str
  system_id: str         # FK to the existing TrackedSystem
  capabilities: list[Capability]
  pol_segments: list[PatternOfLifeSegment]
  events: list[BehaviourEvent]  # events where this is primary_object
  claims: list[Claim]      # free-standing characterisation claims
  # relationships are stored globally, not nested, and indexed by id
  created_at: str
  updated_at: str

class FamilyAssessment(BaseModel):
  """The 'what is this class, what does it do, what is the baseline, what
  should raise concern' synthesis. FACT and assessment kept distinct."""
  id: str
  family_id: str
  one_line: Claim        # the single-sentence characterisation
  role_summary: Claim      # what the class is for
  manoeuvre_baseline: str | None # e.g. "GEO station-keeping 0.5-1 m/s"
  baseline_claim: Claim | None  # provenance for the baseline
  what_raises_concern: list[Claim]  # the analyst's watch-items
  capabilities: list[Capability]   # class-level capabilities
  open_questions: list[str]   # explicit unknowns (the honest gap list)
  validated_by: str | None    # role-holder validation; None == "TBC" per house rule
  created_at: str
  updated_at: str
```

**Note on `validated_by`:** mirrors ENLIGHTENMENT's `validated_by: TBC` pattern. A family
assessment authored by reconstruction (not a role-holder) carries `validated_by = None`
and the UI marks it "awaiting validation". Scored/authoritative use is gated on a
role-holder validating it. **[DECISION - Ash]** confirms the validation route.

---

## 8. Migration from the shipped schema

The shipped store is a JSON file, schema-versioned, with an atomic write and a forward
migration path already established (`src/store.py`). The upgrade adds a migration step.

**Migration contract:**
1. Bump `schema_version` by one.
2. For every existing `TrackedSystem` record, create a companion `CompendiumObject` with
  the same `id` linkage and empty compendium structures (`capabilities: []`,
  `pol_segments: []`, `events: []`, `claims: []`). **No existing field is touched.**
3. Seed the ontology entities (tactics, targets, family assessments, relationships,
  events) from `04-CONTENT-SEED.md` - but only if the store does not already contain
  them (idempotent, exactly like the existing seed logic: never re-seed over live
  edits).
4. The migration is idempotent: running it twice is a no-op on the second run.
5. **Test it against a copy of the real seed store**, asserting all 49 systems survive
  with every original field intact, and the new structures are present and empty (or
  seeded, per step 3).

**Do not** rewrite the store engine. The atomic-write, anti-shrink-merge, archive-not-
delete, backup-before-archive behaviours are load-bearing and tested; the migration is
an additive step within them.

---

## 9. Field-level provenance summary (the rule, restated as a checklist)

For the implementer, the test of whether the model is right:
- [ ] Can any domain claim be shown to an analyst without a source? → must be **no**.
- [ ] Does every capability, event, PoL segment, relationship, target and assessment
   statement carry a `Claim`? → must be **yes**.
- [ ] Is a FACT with no source rejected by validation? → must be **yes**.
- [ ] Is a TBC with no owner rejected by validation? → must be **yes**.
- [ ] Does the migration preserve all 49 existing records unchanged? → must be **yes**,
   proven against a real store copy.
- [ ] Is the object-identity series palette kept separate from the entity-type graph
   palette? → must be **yes** (two distinct CVD-safe sets).
