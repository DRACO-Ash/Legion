# LEGION COMPENDIUM - UI/UX Specification and Claude Design Brief

**Two parts.** Part A is the Claude Design brief: use Claude Design to establish the
visual system and lay out the signature views on a canvas before implementation, so the
look is decided on purpose and can be iterated by eye. Part B is the view-by-view
interaction specification the implementation follows.

**The governing standard** (from the research, `00-RESEARCH-FOUNDATION.md` §4):
*visually striking = restraint + legible hierarchy + purposeful colour + provenance made
visible.* Not decoration. The tool is used at a console, in low light, over long
sessions, by an expert who lives in it. Every pixel earns its place by helping the
analyst move from "what is this object doing" to "what is it, what has it done, what is
it related to, how sure are we" faster than opening seven other tools.

---

## PART A - Claude Design brief

Use Claude Design to produce, on a canvas, the following before writing UI code. Iterate
each by eye against the principles below, then hand the settled design to the
implementation phases. Claude Design is the right tool here because the visual system and
the two signature views (timeline, graph) are design work the analyst will react to and
revise - exactly the case the design canvas is for.

### A1. The visual system (design tokens)
Establish, as a single source of truth, extending the existing Bluestaq house dark
palette already in `src/static/index.html` CSS custom properties:
- **Base surfaces:** the existing navy `#162646` family and panel surfaces (`#152238`,
 etc.). Keep. Low-light console appropriate.
- **Object-identity series palette:** the existing validated 8-slot CVD-safe dark set.
 Do not touch, reorder, or extend. Used ONLY for distinguishing objects in charts.
- **Entity-type palette (NEW):** a separate small categorical set (5–6 slots) for the
 graph's node types (object / family / target / event / tactic). Must be CVD-safe
 against the panel surface and visually distinct from the series palette so an analyst
 never confuses "this is object #3 in the chart" with "this is a family node in the
 graph". Validate with the dataviz skill's `validate_palette.js`.
- **Confidence encoding (NEW):** a redundant triple - colour + icon + line-style - for
 FACT / INFERENCE / SPECULATION. Never colour alone (accessibility + house honesty).
 Suggested: FACT = solid, filled, a "verified" glyph; INFERENCE = dashed, half-tone, an
 "inferred" glyph; SPECULATION = dotted, outline, a "?" glyph. Confirm exact glyphs on
 the canvas.
- **The one attention accent:** a single chart-safe bright for "anomaly / act now"
 (a manoeuvre outside baseline, an unvalidated-but-critical item). NOT copper-amber
 (reserved for documents, house rule). Used sparingly - if everything is urgent,
 nothing is.
- **Typography:** the house stack (Segoe UI family per CONTEXT-001, with the newsletter/
 HTML fallbacks). Establish a type scale with a clear hierarchy: one display size for
 the object/family name (the five-second answer), a body size, a mono size for
 numeric/orbital data (tabular figures for element sets and distances).

### A2. The signature view: pattern-of-life timeline
Design the timeline as the tool's hero visual. On the canvas, lay out:
- A horizontal time axis (the object's history window, matching the existing chart
 windows).
- **Behavioural-mode bands**: coloured horizontal segments (using a small mode palette,
 CVD-safe) showing station-keeping / drift / RPO / etc. over time. A legend maps
 colour+label to mode.
- **Mode-change nodes**: markers at the boundaries, and standalone markers for
 instantaneous events (separation, high-Δv).
- **The raw element-set line overlaid or stacked** beneath, so the analyst sees the raw
 UDL data and the assessed interpretation together, visually distinct.
- **Provenance on hover/focus**: each band and node reveals its claim (marker, source,
 date). The confidence encoding (solid/dashed/dotted) applies to the band edges.
- An empty state: "No assessed behavioural history for this object yet" + why + what to
 do.
Iterate until an analyst can read the object's behavioural story left-to-right in one
glance, and drill into any segment for its provenance.

### A3. The second signature view: relationship graph
Design the graph view:
- Nodes coloured by entity type (the new entity-type palette), sized modestly, labelled.
- Edges styled by confidence (solid/dashed/dotted) with a text label on hover.
- A focus interaction: selecting a node dims the rest and highlights its immediate
 neighbours; the focused node's detail is reachable.
- Filters (nation, regime, behaviour class, confidence floor) as a compact control strip.
- Legible at ~49 objects + families + targets + events. Design the layout so it does not
 become a hairball: consider a force-directed layout with family clustering, or a
 deliberate radial/hierarchical layout keyed off families. Decide on the canvas.
- An empty/withheld state for filtered-to-nothing.

### A4. The object/family detail composition
Design the detail view using the inverted-pyramid + progressive-disclosure pattern:
- **Top (the five-second answer):** name, nation, regime, status, the one-line
 assessment claim, and the single most important capability/flag - all immediately
 visible, with provenance chips.
- **Middle (drill-down):** capabilities, pattern-of-life timeline, related objects
 (graph neighbours), events.
- **Deep (on demand):** the full attribute set, the raw element-set charts, every claim
 with full provenance, open questions.
Iterate until the top answers "what is this and why does it matter" without scrolling,
and everything deeper is one deliberate interaction away.

### A5. The command palette and comparison view
Sketch the keyboard-summoned command palette (jump/filter/switch/compare) and the
side-by-side comparison layout (2–4 objects/families, aligned rows of attributes /
capabilities / baselines). Confirm the interaction model on the canvas.

**Output of Part A:** a settled design token set and canvas layouts for A2–A5, handed to
the implementation phases. Do not start UI code until the visual system and the two
signature views are settled by eye.

---

## PART B - View-by-view interaction specification

The implementation target remains a single-file vanilla-JS SPA served at `GET /`
(the existing architecture - do not introduce a framework; the existing app is a
disciplined single-file SPA and the App Store gate reads it as CSS/JS/HTML). Progressive
enhancement, keyboard-first.

### B1. Global shell
- Persistent left rail or top bar with the primary views: **Catalogue**, **Graph**,
 **Compare**, and a search field. The existing header/brand stays.
- **Command palette**: summoned by a keyboard shortcut (confirm the key on canvas;
 a common choice is Ctrl/Cmd-K). Fuzzy-jump to any object/family/target/tactic; run
 filters; switch view; start a comparison. This is the operability differentiator - 
 an expert never needs the mouse for the core loop.
- Every view is reachable and operable by keyboard; focus order follows reading order;
 ARIA landmarks on shell regions (extend the existing `<main>`/skip-link posture).

### B2. Catalogue view (evolves the existing table)
- Keep the existing paged, filterable table (nation / regime / status / search, the
 existing 15-row paging with the Rows control). It works and is tested.
- Add: a **confidence floor filter** (show only objects whose key claims meet a
 confidence level) and a **behaviour filter** (objects that have demonstrated a given
 mode/tactic).
- Selecting a row opens the **object detail** (B4), not just a chart. The existing
 chart-on-selection becomes part of the detail's deep layer.
- Empty state: honest and specific (existing pattern).

### B3. Graph view (new - Phase 4)
- Renders the ontology per Part A3. Reads the adjacency structure the server assembles.
- Click focuses; double-click (or Enter) opens detail; arrow keys traverse edges.
- Filter strip mirrors the catalogue filters plus entity-type toggles.
- Every edge is provenance-carried; hovering an edge shows its claim.

### B4. Object detail (new composition - Phases 2/3/5)
Per Part A4. The composition, top to deep:
1. Header: name, nation, regime, status, one-line assessment (claim chip), top flag.
2. Capabilities strip: capability chips, each with its confidence marker.
3. Pattern-of-life timeline (Phase 3): the object's behavioural history, with the raw
  element-set chart available.
4. Relative-motion view (Phase 3): when the object has a named counterpart, the ROE
  radial/along-track/cross-track framing.
5. Related entities (Phase 4): the object's graph neighbours, click-through.
6. Events: the dateable close-approaches/manoeuvres/separations, each sourced.
7. Full attributes + all claims + open questions (deep, on demand).

### B5. Family detail (new - Phase 5)
- The **FamilyAssessment**: one-line, role summary, manoeuvre baseline, "what raises
 concern" watch-items, class capabilities, open questions - FACT and assessment
 visually distinct, every statement marked and sourced.
- The family's member objects (the existing family grouping), each linking to B4.
- The family's aggregate pattern-of-life (the class's typical behaviour) where assessed.
- A `validated_by` banner: "awaiting role-holder validation" when `None`.

### B6. Compare view (new - Phase 6)
- Select 2–4 objects/families (from catalogue, graph, or command palette).
- Aligned rows: identity, regime, status, capabilities, manoeuvre baseline, key events,
 confidence of each. Side by side. This is the cross-system comparison use case
 ("which of these has demonstrated a kinetic capability?") made a single view.
- Provenance visible per cell.

### B7. Briefing export (new - Phase 6)
- From any object/family/comparison, generate a house-style textual summary
 (UK English, no em-dashes, lead with the point), with every included claim's provenance
 appended. Ready to paste. Serves the briefing-generation use case.
- The export must not include a claim without its provenance, and must mark any TBC/
 unvalidated content as such - the briefing carries the same honesty as the tool.

### B8. Provenance, everywhere (Phase 2, then all views)
- The confidence chip (colour+icon+text) appears on every claim in every view.
- A persistent legend explains the markers.
- TBC/unvalidated content is always visually distinct and never presented as established.
- This is the feature no other tool foregrounds; it is Legion's distinctive and it is
 the house FACT/INFERENCE/SPECULATION rule made visible.

---

## PART C - Interaction and performance rules (apply throughout)

- **Sub-3-second load, progressive rendering.** Render partial data as it arrives (the
 app already learned this for storage). The graph and timeline must not block the shell.
- **Keyboard-first.** Every action in the core loop (find → characterise → compare →
 brief) is keyboard-operable. Mouse is an accelerator, not a requirement.
- **Empty/error states are onboarding moments** (NN/g; and the exact CONTEXT-001 lesson).
 Name the reason, name the remedy. Never a bare "no data".
- **No colour-alone encoding** of confidence or object identity. Redundant encodings
 throughout (colour + icon + text; colour + line-style + label).
- **Respect the five chart rules** (CONTEXT-001): one metric one axis; colour follows the
 satellite; rank-gate; relative-mode anchors on the latest element set; the palette is
 the validated set. The new timeline and graph use their OWN palettes (mode palette,
 entity-type palette) - kept separate from the object-identity series palette.
- **Drive the real page before believing any message.** The single most-repeated bug in
 this project's history is a UI message naming something it cannot see. Every new view's
 messages are verified in a browser, not by reading the code.
