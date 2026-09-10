# Research strand 4: Operational UI/UX and the ontology-graph paradigm

## The dominant paradigm for elite intelligence tools: ontology + graph
Sources: Palantir Gotham platform analyses; the "AEGIS / Palantir-Gotham-like" open
implementation; Gotham dynamic-ontology papers.

The defining idea, stated bluntly across every source: **"the most dangerous threats
hide in the relationships between things you have already seen."** Gotham's power is not
the data store; it is:
1. **The ontology** - a formal model of the entity types in the domain (people, places,
  objects, events) and the relationship types between them. "The ontology is the
  instruction manual."
2. **The graph** - entities connected by relationships, navigable. "The graph is the
  seeing stone." Gotham models "relationships between people, places, objects and
  events" and supports "targeting, sensor-tasking and operational workflows."
3. **Propagating security** - permissions follow the data through analysis and
  dissemination. (Legion's classification/redaction discipline is the analogue.)

→ THE central architectural upgrade for Legion: move from a FLAT CATALOGUE of objects to
an ONTOLOGY of the threat domain. Entity types: Object (satellite), Family/Programme,
Behaviour/Tactic, Event (manoeuvre, separation, close approach), Target (the thing being
threatened), Nation/Operator, Source. Relationship types: belongs-to-family,
coplanar-with, shadowed, birthed, approached, demonstrated-tactic, threatens,
sourced-from. The analyst's core question - "what is this thing, what has it done, what
is it related to" - is a graph traversal, not a row lookup.

This does NOT mean shipping Neo4j. For ~49 objects and a dozen families the graph is
small; it can live in the same JSON store as an adjacency structure and be rendered
client-side. The POINT is the data MODEL and the navigation, not the database engine.
Legion's existing "family" grouping is the embryonic form of this - the upgrade is to
make relationships between objects, behaviours, and events first-class and navigable.

## Operational vs. analytical vs. strategic dashboards (know which Legion is)
UXPin taxonomy: analytical (trend analysis), operational (real-time monitoring),
strategic (exec KPIs), tactical (short-term). **Legion is primarily ANALYTICAL +
REFERENCE, with an operational edge during a live event.** It is not a real-time
monitoring wall (that is a different tool). This matters for the design: the analyst is
usually investigating/characterising/learning, occasionally reacting. So the design
optimises for DRILL-DOWN and COMPARISON, not for a always-on alert firehose.

## The transferable UI/UX principles (all convergent across 2025-26 sources)
1. **Five-second rule + inverted pyramid.** The one thing the analyst must grasp in
  <5s goes top/centre with strong visual weight; detail drills down. For Legion: on
  selecting an object, the "what is this and why does it matter" answer is immediate;
  the element-set history, sources, and full attribute set are progressive.
2. **Progressive disclosure is THE pattern for data-dense tools.** "Show what matters
  now, hide what doesn't." Secondary data lives behind a deliberate interaction.
  NN/g: reduces cognitive load up to ~55%. Legion's current single-scroll admin form
  shows everything at once - the opposite. Summary card → expand → full record.
3. **Functional minimalism.** Every element serves comprehension; anything that doesn't
  is removed. "Not to impress with visual flourishes." Visually striking must come from
  restraint + hierarchy + purposeful colour, NOT decoration. (This aligns with the
  dataviz-skill palette discipline already in CONTEXT-001.)
4. **Accessibility is a design multiplier, not a tax.** Section 508 / WCAG discipline
  (contrast, no colour-alone encoding, keyboard nav, reading order) "consistently
  produce layouts that test better with ALL users." Government-grade constraint →
  better tool for everyone. Legion already has WCAG-AA contrast + CVD-safe palette
  discipline; extend it (keyboard-first navigation, ARIA on the graph/timeline).
5. **Empty and error states are onboarding moments.** "No data? Explain why, suggest an
  action." This is EXACTLY the lesson of the failed research JSON and CONTEXT-001's
  repeated "a message that names something it cannot see" bug: the honest, specific,
  actionable empty state is an operational feature. When a chart can't be drawn, say
  why (rank gate, feed down, no element sets) and what the analyst can do.
6. **Keyboard-driven operation / command palette.** For an expert tool used daily, a
  command palette (jump to object, filter, compare, switch view) and full keyboard
  navigation is what separates a console-grade tool from a web form. Analysts live in
  the tool; mouse-only is friction. This is a concrete operability upgrade over any
  flat catalogue.
7. **Sub-3-second load, progressive loading.** Users expect <3s. Legion's server-side
  assembly + TTL cache already respects this; keep it, and render partial data as it
  arrives (the app already learned "display data progressively" for storage).

## Visually striking, done right (for the Claude Design phase)
The brief wants "visually striking and operability that surpasses any known tactics
tool." Synthesis of what that actually means for THIS tool:
- Dark operational theme (already the Bluestaq house dark palette: navy #162646,
 blues, the validated 8-slot CVD-safe dark dataviz set). Strong for a console used in
 low light, reduces eye strain over long sessions. KEEP and systematise.
- The striking-ness comes from: a genuinely legible information hierarchy; a
 pattern-of-life TIMELINE as a signature visual (nodes + modes, not a plain line);
 a relationship GRAPH as a second signature visual; and confidence/provenance made
 visible (colour + icon + label, never colour alone) so the analyst SEES the epistemic
 status of every claim. Nobody else's tool foregrounds provenance as a design element;
 that is Legion's distinctive, and it is directly downstream of the house
 FACT/INFERENCE/SPECULATION rule.
- Restraint: one accent for "act now / anomaly", the CVD palette for object identity,
 everything else in the neutral dark scale. The copper-amber is reserved for documents
 per house style and must NOT enter the product UI (CONTEXT-001 rule) - so the
 in-product "attention" accent is a chart-safe bright, not copper.

## What to explicitly NOT do (scope discipline)
- Not a real-time monitoring wall / not a replacement for the SSA provider feeds.
- Not a 3D globe in v1 (CONTEXT-001 already ruled this for ENLIGHTENMENT; same logic - 
 a 2D, legible, fast tool beats an impressive slow globe for the analytic task).
- Not a heavy graph-database deployment for 49 objects.
- Not multiple-choice/quiz framing (that is ENLIGHTENMENT's job; Legion is reference).
- Not fabricated data to fill the ontology - every node/edge carries provenance or is
 explicitly marked TBC. The research JSON's honesty is the standard.
