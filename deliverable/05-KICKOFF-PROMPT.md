# LEGION COMPENDIUM UPGRADE - Claude Code Kick-off Prompt

Paste the block below as the first message to Claude Code, in the `legion` repository,
with this `deliverable/` folder present at the repo root (alongside `CLAUDE.md`,
`HANDOFF.md`, `READINESS.md`).

---

```
You are working in the legion repository - a shipped, live, App-Store-passing FastAPI
application (currently v0.9.2). We are upgrading it from a flat threat catalogue into a
provenance-first ontology of the threat domain: a best-in-class knowledge compendium for
threat satellite systems used by orbital warfare analysts.

READ FIRST, IN THIS ORDER, BEFORE WRITING ANY CODE:
1. CLAUDE.md - the standing rules, the shipped state, the App Store gate constraints, the
  five Code Quality conditions, the three container rules, the no-auth decision, the
  five chart rules, and the "verify against the real thing" discipline. All still apply.
2. HANDOFF.md and READINESS.md - history and current posture.
3. deliverable/00-RESEARCH-FOUNDATION.md - why the upgrade is shaped this way (the
  research evidence base: MITRE ATT&CK design principles, the CSIS/SWF threat domain,
  the pattern-of-life SDA model, and the ontology-graph paradigm).
4. deliverable/01-BUILD-SPECIFICATION.md - the phased plan and the prime directives.
5. deliverable/02-DATA-MODEL.md - the exact schema (the Claim atom, capabilities, events,
  pattern-of-life, relationships, targets, composed entities, and the migration).
6. deliverable/03-UI-UX-SPECIFICATION.md - the interface and the Claude Design brief.
7. deliverable/04-CONTENT-SEED.md - the sourced, provenance-carried domain content.

NON-NEGOTIABLE CONSTRAINTS (from CLAUDE.md and the spec):
- This app is shipped and gate-passing. Every change is additive or a carefully tested
 refactor. Do not break the ten App Store stages. Before touching requirements*.txt, the
 Dockerfile, or sonar-project.properties, read docs/APP-STORE-DEPENDENCY-SCANNING.md and
 the relevant CLAUDE.md sections.
- Provenance is structural. Every domain claim carries FACT/INFERENCE/SPECULATION, a
 confidence, a source, a source-class, and a date (the Claim type). A FACT with no source
 is rejected; a TBC with no owner is rejected. No unsourced claim reaches the analyst
 view. Never fabricate a value, date, catalogue number, or citation.
- The existing charting engine and the five chart rules are load-bearing. Build on them;
 do not replace them. Keep the object-identity series palette separate from the new
 graph entity-type palette and the timeline mode palette. Do not touch, reorder, or
 extend the validated 8-slot CVD-safe series palette.
- No authentication (it was a decision). No 3D globe in v1. No graph database. No
 framework - stay a single-file vanilla-JS SPA. No classified data or real operational
 thresholds in the repo. UK English, no em-dashes, lead with the point.
- Extend the existing test mirrors (test_sonar_contracts, test_sonar_cognitive_complexity,
 test_ui_contracts) to cover new UI/JS. Every new fetch path and rendered field goes into
 the UI contract tests. Every release changes a real src Python file (the coverage-
 measurability trap). Verify every UI message by driving the real page in a browser.

HOW TO PROCEED:
- Do the work in the six phases defined in 01-BUILD-SPECIFICATION.md, in order. Each phase
 is independently shippable and must leave the app gate-passing with tests green.
- Start with Phase 1 (data model + migration) only. It is pure schema, carries the highest
 risk to the shipped app, and everything else depends on it. Prove the migration against
 a copy of the real seed store: all 49 systems survive with every field intact.
- For the UI phases, use Claude Design first (per 03-UI-UX-SPECIFICATION.md Part A) to
 settle the visual system and the two signature views (pattern-of-life timeline,
 relationship graph) on a canvas before writing UI code.
- Some decisions are marked [DECISION - Ash] in the spec (classification marking, nation
 scope, family-assessment validation route, two UDL endpoint confirmations, the
 relative-motion frame source). Do NOT guess these. When you reach a phase that depends on
 one, stop and ask.

FIRST ACTIONS, RIGHT NOW:
1. Confirm you have read all seven documents and state, in your own words, the single
  analytical reason this tool exists (the capability + context + pattern-of-life
  disambiguation from the research) - so we know the intent is understood, not just the
  task list.
2. Produce a step-by-step Phase 1 build plan: the exact models to add, the migration
  approach, the tests to write, and how you will prove the 49 records survive. Name the
  files you will touch. Call out anything in the spec that is unclear or that you think is
  wrong.
3. Wait for my go-ahead before writing any code.
```

---

## Notes for Ash (not part of the paste)

- The seven `[DECISION - Ash]` items are collected here for your convenience; Claude Code
 will stop and ask when it hits each, but you can pre-empt them:
 1. **Classification marking** of the richer capability/intent content.
 2. **Nation scope** - stay RU/CN, or widen to the full open-source picture (Iran, DPRK,
   India, dual-use commercial).
 3. **Family-assessment validation route** - who is the role-holder that validates a
   `FamilyAssessment` before it is authoritative, mirroring ENLIGHTENMENT's expert-trace
   gate.
 4. **UDL `/udl/elset/history`** and the notification **`window_hours`** semantics - still
   INFERENCE in CONTEXT-001; the pattern-of-life history depth depends on the former.
 5. **Relative-motion frame source** - the UDL path and allowed query pattern for pulling
   a target object's element sets (avoid the forbidden per-object query loop).

- The research is captured in full in `research/` (four strands) and synthesised in
 `deliverable/00-RESEARCH-FOUNDATION.md`. If you want the raw research notes in the repo
 as well, they are worth committing alongside the deliverable so the "why" travels with
 the code, the same way CONTEXT-001 and CLAUDE.md already do.

- The single most valuable thing this upgrade adds, if you strip everything else away: the
 tool stops being a list of objects and becomes a way to answer "what is this thing
 capable of, what has it done, what is it related to, and how sure are we" - which is
 exactly the question the CSIS report says behaviour data alone cannot answer, and
 exactly the question a JCO analyst is under pressure to answer during a live event.
```
