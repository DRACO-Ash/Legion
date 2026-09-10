# LEGION COMPENDIUM UPGRADE - Build Specification for Claude Code

**Audience:** Claude Code, executing against the existing `legion` repository (currently
v0.9.2, shipped and live on the Bluestaq App Store).

**Status of this document:** a complete engineering specification. It is opinionated and
detailed on purpose - the brief was to leave nothing to guesswork. Every feature below
has a stated analyst benefit traced to `00-RESEARCH-FOUNDATION.md`. Where a decision is
genuinely open, it is marked **[DECISION - Ash]** and must not be guessed.

**How to read this set:**
- `00-RESEARCH-FOUNDATION.md` - why the design is shaped this way (read first).
- `01-BUILD-SPECIFICATION.md` - this file: what to build, in phases, with acceptance
 criteria.
- `02-DATA-MODEL.md` - the exact schema: entities, fields, relationships, enums,
 migration.
- `03-UI-UX-SPECIFICATION.md` - the interface, view by view, and the Claude Design brief.
- `04-CONTENT-SEED.md` - the sourced domain content to load, with provenance.
- `05-KICKOFF-PROMPT.md` - the prompt to paste into Claude Code to begin.

---

## 0. Prime directives (do not violate these)

These are lifted from the shipped `CLAUDE.md` and CONTEXT-001. They are not negotiable
and they constrain every phase below.

1. **This is a working, shipped, gate-passing application. Do not break it.** Every
  change is additive or a careful refactor with tests green before and after. The App
  Store gate has five Code Quality conditions, a Container Scan with three easily-undone
  rules, and a Dependency Scanning gate that cost six upload cycles. Read
  `docs/APP-STORE-DEPENDENCY-SCANNING.md` and the "Code Quality gate has five
  conditions" section of `CLAUDE.md` before touching `requirements*.txt`, the
  `Dockerfile`, or `sonar-project.properties`.

2. **Provenance is structural, not decorative.** Every domain claim the compendium
  displays carries: the assertion, a confidence marker (FACT / INFERENCE / SPECULATION),
  a confidence level, a source, a source-class, and a date. This is the house rule made
  into a schema. No free-text field is allowed to smuggle an unsourced claim into the
  analyst's view. The failed research JSON (`legionfamilyresearchUNVERIFIED.json`) is
  the cautionary example: it correctly recorded "could not verify" rather than
  fabricating, and that honesty is the standard.

3. **No fabricated data. Ever.** Unknown means a record marked `TBC, re-verify` with a
  named owner, never an invented value, date, catalogue number, or citation. This holds
  for seed content, for ontology edges, and for anything a model generates.

4. **The existing charting engine is high-quality - build on it, do not replace it.**
  `src/static/index.html`'s SVG charts already handle longitude unwrapping,
  relative/absolute anchoring on the latest element set, and a CVD-safe 8-slot palette
  read from CSS. The five chart rules in CONTEXT-001 ("one metric one axis", "colour
  follows the satellite", rank-gate, etc.) are load-bearing. Extend, do not rewrite.

5. **Palette discipline.** The validated 8-slot CVD-safe dark dataviz palette is held
  once in CSS custom properties; never reorder it, never add a ninth. Copper-amber is
  reserved for documents and must not enter the product UI. Re-run the dataviz skill's
  `validate_palette.js` against the panel surface if the palette changes.

6. **UK English, no em-dashes, lead with the point.** House style, everywhere, including
  in-app copy and code comments.

7. **Verify against the real thing.** The project has a documented history of failures
  caused by asserting instead of testing. Drive the real page in a browser before
  believing any UI message; run the real platform command against a fresh venv before
  believing an install works; build the real container before believing the Dockerfile
  is correct.

---

## 1. What is changing, in one paragraph

Legion becomes a **provenance-first ontology of the threat domain** with three signature
capabilities the current flat catalogue lacks: (a) a **pattern-of-life timeline** per
object - behavioural modes and mode-change nodes over time, not just a raw element-set
line; (b) a **relationship graph** - objects, families, behaviours, events, and targets
connected and navigable, because "the most dangerous threats hide in the relationships
between things you have already seen"; and (c) a **capability + context + intent layer**
per object and per family - the disambiguation data that behaviour alone cannot provide,
which is the analytical reason the tool exists. All three are wrapped in a data-dense,
progressive-disclosure, keyboard-navigable dark console, and every claim they surface
carries visible provenance. The disciplined engineering that already clears the App
Store gate is preserved throughout.

---

## 2. Phasing

The upgrade is delivered in **six phases**, each independently shippable, each leaving
the app gate-passing. Do not attempt the whole thing in one branch. Each phase has an
explicit "done" bar. Version bumps follow the existing `scripts/bump_version.sh` flow.

**Ordering rationale:** the data model must land before the views that read it; the
ontology before the graph that renders it; the seed content before the analyst can
judge whether a view is useful. Phase 1 is pure schema and carries the highest risk to
the shipped app, so it is done first, small, and fully tested.

### Phase 1 - Extend the data model (schema + store + migration)
Foundational. Adds the compendium's richer entity shape *alongside* the existing
`TrackedSystem`, with a forward migration that never drops an existing field. No UI
change. See `02-DATA-MODEL.md` for the exact schema.

Deliverables:
- New Pydantic models: `Claim` (the provenance-carrying unit), `Capability`,
 `BehaviourEvent`, `PatternOfLifeSegment`, `Relationship`, and an extended
 `CompendiumObject` / `CompendiumFamily` that compose them.
- `src/store.py` extended with a versioned migration (`schema_version` bump) that
 upgrades every existing record in place, additively. Existing records gain empty
 compendium structures; nothing is lost. The migration is idempotent and tested against
 a copy of the real seed store.
- Round-trip tests: create → read → update (anti-shrink) → archive for every new entity,
 plus a migration test that loads a v(current) store and asserts a clean v(next) store
 with all 49 records intact.

**Done when:** `pytest` green, coverage on new code ≥ 80%, the migration proven on a
real store copy, and `GET /api/systems` still returns the 49 records unchanged in their
existing fields. No visible product change yet.

### Phase 2 - The claim / provenance layer (API + minimal UI surfacing)
Makes provenance real end to end before building the big views on top of it.

Deliverables:
- CRUD API for `Claim`s attached to any object or family
 (`/api/objects/{id}/claims`, etc.), reads public, writes rate-limited (matching the
 existing open-write posture - there is no auth, that was a decision; see
 `CLAUDE.md`).
- Every claim renders in the existing object detail view with its confidence marker as a
 visible chip (colour + icon + text label - never colour alone), its source, source-
 class, and date.
- A provenance legend in the UI explaining the markers.

**Done when:** an analyst can see, for any seeded claim, its FACT/INFERENCE/SPECULATION
status, confidence, source and date, in the browser, with the marker legible to a
colour-blind user and to a screen reader.

### Phase 3 - Pattern-of-life timeline (the first signature visual)
The behavioural-history upgrade. Builds on the existing chart engine.

Deliverables:
- `PatternOfLifeSegment` sequence per object (mode + start/end nodes), rendered as a
 timeline band beneath/alongside the existing element-set chart, using the same CVD
 palette and the same server-assembled data path.
- Mode-change nodes overlaid on the existing element-set line as markers, with the mode
 vocabulary from `02-DATA-MODEL.md`.
- Where an object has a named target/coplanar counterpart, a **relative-motion** view
 option (radial / along-track / cross-track framing) - this is the ROE upgrade from the
 research. Reuse the relative-mode machinery already in the chart code.

**Done when:** selecting an object shows its behavioural history as a legible timeline;
the modes are the controlled vocabulary; the relative-motion view works for at least the
COSMOS-2576/USA-314 and SJ-25/SJ-21 pairs; all five existing chart rules still hold
(verified in a browser).

### Phase 4 - The relationship graph (the second signature visual)
The ontology made navigable.

Deliverables:
- A graph view: nodes = objects/families/targets/events, edges = the relationship types
 from `02-DATA-MODEL.md`. Rendered client-side (no graph DB) from an adjacency
 structure the server assembles.
- Click-to-navigate: selecting a node focuses it and reveals its neighbours; double-click
 opens its detail. Keyboard-navigable (arrow to traverse edges, Enter to open).
- Edges carry provenance too (a "coplanar-with" edge sourced from a specific assessment).
- Filtering: by nation, regime, behaviour class, confidence floor.

**Done when:** an analyst can start from one object and reach every related object,
family, event and target by traversal; the graph is legible at ~49 objects + their
relationships; it is fully keyboard-operable; and no edge is unsourced.

### Phase 5 - Capability + context + intent layer (the analytical core)
The disambiguation data that is Legion's reason to exist.

Deliverables:
- `Capability` records per object/family (e.g. "robotic arm", "demonstrated
 noncooperative capture", "SIGINT payload", "kinetic-kill vehicle ejection"), each a
 provenance-carrying claim.
- A per-family **assessment** panel: the "what is this class, what does it typically do,
 what is the baseline manoeuvre signature, what should raise concern" summary - the
 capability + context + pattern-of-life synthesis, structured so FACT and assessment
 are visually distinct (the BattlePolicy "reference entry vs. analyst assessment" split,
 done honestly with provenance).
- A **class-baseline** field per family (e.g. GEO station-keeping 0.5–1 m/s) so a
 deviation in the live UDL charts is legible as a deviation, not just a number.

**Done when:** for any family, an analyst can read the capability + context + intent
synthesis, see the class manoeuvre baseline, and every assessment statement is marked
FACT / INFERENCE / SPECULATION with a source.

### Phase 6 - Operability layer (command palette, keyboard, comparison, briefing)
The "surpasses any known tactics tool" operability.

Deliverables:
- A **command palette** (keyboard-summoned) to jump to any object/family, switch view,
 filter, or start a comparison, without the mouse.
- Full keyboard navigation across the catalogue, graph, and timeline.
- A **comparison view**: select 2–4 objects/families and see their attributes,
 capabilities, and baselines side by side (the cross-system comparison use case).
- A **briefing export**: generate a house-style summary of a selected object/family/
 comparison, provenance included, ready to paste - serving the briefing-generation use
 case. Reuse Bluestaq house-style rules.

**Done when:** an analyst can operate the core loop (find → characterise → compare →
brief) entirely from the keyboard, and a generated briefing carries the provenance of
every claim it includes.

---

## 3. Cross-cutting requirements (apply to every phase)

- **Testing bar:** the existing local SonarQube mirrors (`tests/test_sonar_contracts.py`,
 `tests/test_sonar_cognitive_complexity.py`, `tests/test_ui_contracts.py`) must be
 extended to cover new UI/JS, not just left as-is. `tests/test_ui_contracts.py` already
 pins that every path the UI fetches exists in the OpenAPI schema and that catalogue
 values are escaped before markup - every new fetch path and every new rendered field
 must be added to these contracts. This is how the "message that names something it
 cannot see" class of bug is prevented.
- **Coverage-measurability trap:** every release must change a Python file under `src`
 (not just `tests/` or static assets) or the `code-quality-verify` job fails with
 "coverage was not measured". `bump_version.sh` warns on this. Plan phase commits so
 each carries a real source change.
- **Empty/error states are features.** Every view must have an honest, specific,
 actionable empty state (why is there nothing here, what can the analyst do). Follow the
 existing rank-gate message pattern: name the reason (rank gate, feed down, no element
 sets, unsourced-so-withheld) and the remedy.
- **Provenance everywhere or withhold.** If a claim has no source, it is not shown in the
 analyst view as fact; it is either marked TBC or withheld with an explanation. Never
 silently present the unsourced as sourced.
- **Performance:** sub-3-second load, progressive rendering, the existing TTL cache
 respected. The graph and timeline must render at 49 objects without jank; if the object
 count grows, they must degrade gracefully (cluster, paginate) not freeze.
- **Accessibility:** WCAG-AA contrast (already disciplined), keyboard-first, ARIA on the
 graph and timeline, no colour-alone encoding of confidence or object identity. Extend
 the existing accessibility posture; do not regress it.

---

## 4. What NOT to build (explicit scope fence)

- **Not** a real-time monitoring wall / alert firehose. Legion is analytical + reference
 with an operational edge. The live-monitoring job belongs to a different tool.
- **Not** a 3D globe in v1. A fast, legible 2D tool beats an impressive slow globe for
 the analytic task (same logic CONTEXT-001 applied to ENLIGHTENMENT).
- **Not** a graph database deployment. The graph is small; it lives in the JSON store and
 renders client-side.
- **Not** authentication. It was removed as a decision (`CLAUDE.md`); the platform in
 front is the access control. Do not reintroduce a token. `tests/test_ui_contracts.py`
 and `tests/test_security.py` guard this.
- **Not** multiple-choice / quiz framing. That is ENLIGHTENMENT's job; Legion is
 reference and characterisation.
- **Not** any classified data or real operational thresholds in the repository. The
 compendium is built from open-source assessments (CSIS, SWF, and the like) with
 provenance. If a field would require classified input, it is a `TBC, re-verify` with a
 named owner, never populated from assumption.

---

## 5. Open decisions that must not be guessed **[DECISION - Ash]**

1. **Classification marking of the compendium itself.** The current app is unclassified
  open-source-derived. The richer capability/intent assessments, even when built from
  open sources, may warrant a marking above the raw catalogue. Confirm the marking
  before any assessment content ships, per the house rule that classification is never
  assumed.
2. **Scope of nations.** The current catalogue is Russia + China. The research shows the
  open-source threat picture also covers Iran, North Korea, India, and dual-use
  commercial actors. Confirm whether the compendium stays RU/CN or widens.
3. **Whether family assessments are authored in-app or imported.** The seed content in
  `04-CONTENT-SEED.md` is drafted from open sources with provenance, but a role-holder
  should validate each family assessment before it is treated as authoritative (the
  same gate ENLIGHTENMENT applies to expert traces). Confirm the validation route.
4. **UDL endpoints still marked INFERENCE.** `/udl/elset/history` and the notification
  `window_hours` semantics remain unconfirmed against a live UDL session (CONTEXT-001).
  The pattern-of-life timeline's history depth depends on the former. Confirm before the
  timeline's history depth is trusted operationally.
5. **Relative-motion frame source.** The ROE relative-motion view needs a target
  object's element sets as well as the threat object's. Confirm the UDL path and the
  allowed query pattern (per-object vs. batched) before building the fan-out, to avoid
  the forbidden per-object query-loop pattern (CONTEXT-001 Space-Track rule; confirm the
  UDL equivalent).

Do not proceed past the phase that first depends on each decision until it is answered.
