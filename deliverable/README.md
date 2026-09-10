# LEGION Compendium Upgrade - Specification Package

**What this is.** A complete, research-grounded engineering specification to take the
shipped `legion` application (v0.9.2, live on the Bluestaq App Store) from a flat threat
catalogue to one of the best knowledge compendiums for threat satellite systems in
existence - built for the orbital warfare analyst, with every feature traced to a
tangible analyst benefit and every claim carrying its provenance.

**How it was produced.** A deep-dive research task across four strands (how the world's
best threat knowledge bases work; the counterspace threat domain; SDA pattern-of-life
tradecraft; operational intelligence-tool UI/UX), reading primary sources including the
full CSIS *Space Threat Assessment 2025*, the MITRE ATT&CK design philosophy, the SDA
pattern-of-life literature, and the Palantir-Gotham ontology paradigm. That research was
then applied to the actual shipped codebase to specify a phased, non-breaking upgrade.

---

## The one-paragraph thesis

The best threat compendium is **an empirically-grounded, provenance-first ontology of the
threat domain** - objects, families, behaviours, events, and their relationships - that
lets an analyst move from *"what is this object doing right now"* to *"what is it capable
of, what has it done before, what is it related to, and how sure are we"* in a few
keystrokes, at a console, faster than opening seven other tools. The CSIS assessment is
explicit that **behaviour data alone cannot distinguish a weapon from a surveillance
asset** - you need capability + context + pattern-of-life. That is precisely the layer
Legion lacks today and precisely what this upgrade adds, without losing the disciplined,
tested, gate-passing engineering already in place.

---

## What changes (three signature capabilities the flat catalogue lacks)

1. **Pattern-of-life timeline** - each object's behavioural history as modes and
  mode-change nodes over time (the formal SDA pattern-of-life model), overlaid on the
  existing element-set charts. The analyst reads an object's story left to right.
2. **Relationship graph** - objects, families, behaviours, events, and targets connected
  and navigable, because *"the most dangerous threats hide in the relationships between
  things you have already seen"* (the Palantir-Gotham ontology paradigm), rendered
  client-side, no graph database.
3. **Capability + context + intent layer** - the disambiguation data behaviour alone
  cannot provide, per family and per object, with the class manoeuvre baseline so a
  deviation in the live charts is legible as a deviation.

All three are wrapped in a data-dense, progressive-disclosure, keyboard-navigable dark
console, and **every claim they surface carries visible provenance** (FACT / INFERENCE /
SPECULATION + confidence + source + date) - the house epistemic rule made into a schema
and a design element. No other tool foregrounds provenance this way; it is Legion's
distinctive.

---

## The documents, in reading order

| File | What it is |
|---|---|
| `00-RESEARCH-FOUNDATION.md` | The evidence base. Why the design is shaped this way. Read first. |
| `01-BUILD-SPECIFICATION.md` | The phased build plan (six phases), prime directives, scope fence, and the open decisions that must not be guessed. |
| `02-DATA-MODEL.md` | The exact schema: the `Claim` atom, capabilities, events, pattern-of-life, relationships, targets, composed entities, and the non-breaking migration. |
| `03-UI-UX-SPECIFICATION.md` | The interface, view by view, plus the Claude Design brief for the visual system and the two signature views. |
| `04-CONTENT-SEED.md` | The sourced, provenance-carried domain content to load, drawn from the research with a source key. |
| `05-KICKOFF-PROMPT.md` | The prompt to paste into Claude Code to begin, and the collected `[DECISION - Ash]` items. |
| `research/` | The four raw research strands, in full, so the "why" travels with the code. |

---

## How to use it

1. **Read `00`** to understand the intent, then skim `01`–`04`.
2. **Answer the five `[DECISION - Ash]` items** (collected in `05`) when you can - 
  classification marking, nation scope, family-assessment validation route, two UDL
  endpoint confirmations, and the relative-motion frame source. Claude Code will stop
  and ask when it reaches each, but pre-empting them keeps it moving.
3. **Upload the `legion` zip to Claude Code**, drop this `deliverable/` folder at the repo
  root, and paste the block from `05-KICKOFF-PROMPT.md` as the first message.
4. Claude Code will confirm it understands the analytical intent, produce a Phase 1 plan
  (data model + migration, the highest-risk-to-shipped part, done first and small), and
  wait for your go-ahead before writing code.

---

## What this deliberately does not do

Not a real-time monitoring wall (that is a different tool). Not a 3D globe in v1 (a fast
legible 2D tool beats an impressive slow one for the analytic task). Not a graph database
(the graph is small). Not authentication (removed as a decision; the platform fronts
access). Not multiple-choice/quiz framing (that is ENLIGHTENMENT's job). Not one line of
fabricated data (unknown means a sourced `TBC` with a named owner). And not a rewrite - 
the shipped charting engine, the store, the test discipline, and the gate-passing
posture are preserved and built upon throughout.

---

## The honesty thread

The prior research attempt (`legionfamilyresearchUNVERIFIED.json`) returned almost empty
because its verification step could not reach its sources - and it recorded that failure
honestly rather than fabricating. That honesty is the standard this whole specification is
built to enforce structurally: the `Claim` type rejects a fact with no source and a TBC
with no owner; the seed content loads single-source claims at moderate confidence, not
high; family assessments render "awaiting validation" until a role-holder signs them off.
A compendium that quietly presents the unsourced as established would mislead the analyst
at exactly the moment they can least afford it. This one cannot.
