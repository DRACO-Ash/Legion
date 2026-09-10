# LEGION - Research Foundation for the Compendium Upgrade

**Purpose of this document.** This is the evidence base underneath the build
specification in `01-BUILD-SPECIFICATION.md`. It records what was researched, from
which sources, and what each finding implies for Legion. Nothing in the specification
is asserted without a trail back to here. Read this once to understand *why* the
specification is shaped the way it is; consult the specification itself to build.

**Provenance discipline.** Every external claim below is attributed. Where a source is
an open-source assessment (CSIS, SWF), the claim is FACT-at-the-level-of "this
organisation assessed this from open sources" - not ground truth about a classified
system. This mirrors Legion's own house rule (FACT / INFERENCE / SPECULATION) and is
exactly the discipline the compendium must enforce structurally.

---

## 1. How the world's best threat knowledge bases actually work

**Reference standard: MITRE ATT&CK** (Strom, Applebaum et al., *ATT&CK: Design and
Philosophy*, MITRE, 2018/2020; and the *ATT&CK for ICS Philosophy* paper, 2020).

Five transferable design principles, each with its Legion implication:

1. **Mid-level abstraction is the whole game.** ATT&CK deliberately sits between the
  too-abstract (Cyber Kill Chain, 7 linear stages) and the too-specific (CVE/hash
  databases). The mid level is "specific enough to relate an adversary action to a
  specific way of defending against it, general enough to span many concrete cases."
  → Legion entries must sit where an analyst can *act*: not "COSMOS-2519 exists" (too
  low) and not "Russia does co-orbital RPO" (too high), but "this class shadows a
  target by matching its plane, and here is the observable that reveals it."

2. **One taxonomy, understood by both sides.** Tactics = goals (why); techniques =
  methods (how); procedures = in-the-wild executions. Same vocabulary for the red
  actor and the blue analyst.
  → Legion needs a shared vocabulary spanning the threat behaviour *and* the analyst's
  response (what the JCO operator watches for, reports, and does).

3. **Empirically grounded, never speculative.** Every technique is backed by observed
  use, with citations; circumstantial evidence is flagged as such.
  → Direct match to the house FACT/INFERENCE/SPECULATION rule. The compendium format
  must *enforce* provenance, not merely allow it. The current free-text `notes` field
  does not.

4. **Consistent abstraction across entries** (the 2020 sub-technique reform). Uniform
  depth is what makes cross-entry comparison valid. Sub-techniques have exactly one
  parent to keep the model maintainable.
  → Every family/object entry must be filled to the same shape, or the analyst's core
  task (cross-system comparison) silently breaks. A required-field schema enforces this.

5. **Built for multiple driving use cases at once**, decided up front.
  → Legion's driving use cases, decided here: (a) rapid threat characterisation during
  a live event; (b) training a new Space Event Analyst; (c) pattern-of-life baseline
  vs. current behaviour; (d) cross-system comparison; (e) briefing generation.

**Adjacent CTID projects worth stealing conceptually:**
- **Attack Flow** (CTID, 2022/2026): model the *sequence* of an attack, not isolated
 techniques. "Defenders think in lists, adversaries think in graphs." → A threat
 satellite's behaviour is a *sequence* (launch → commissioning → drift → co-planar
 approach → shadow → separation → …). Modelling the sequence is the single biggest
 conceptual upgrade available.
- **Summiting the Pyramid** (CTID, 2026): measure detection *depth and quality*, not
 binary presence. → A coverage/confidence layer: for each behaviour, how well can we
 actually observe it (sensor coverage, revisit, photometric availability)? The
 analyst's honesty layer.
- **Pyramid of Pain** (Bianco): rank indicators by cost-to-adversary; TTPs at the top
 hurt most. → Key the compendium off durable observables (orbital mechanics, manoeuvre
 signatures, hardware constraints) not the things an adversary trivially changes
 (naming, cover stories).

**Precedent for the live-editable model: US Army milWiki** (army.mil, 2009). The Army
tested a wiki for TTPs because the field-manual cycle was 3–5 years and could not keep
pace. → Validates Legion's live, versioned JSON store over any document-cycle approach.
It also flags that *governance* (who asserts what, how sure) matters - the compendium
needs an editorial/provenance layer even without login auth.

Full detail: `research/01_kb_design_principles.md`.

---

## 2. The counterspace threat domain (the analyst's operational picture)

**Primary source: CSIS *Space Threat Assessment 2025*** (Swope, Bingen, Young, LaFave,
April 2025 - full report read). Eight years of continuous open-source assessment; the
reference document an orbital warfare analyst uses.

**The counterspace weapon taxonomy** (Legion's classification spine). Four categories - 
kinetic, non-kinetic, electronic, cyber - each differentiated by an axis-set CSIS uses
that maps *directly* onto attributes Legion should carry per system: origin→destination
(ground/space), permanence, scale of effect, attributability, requires-launch,
requires-SDA-to-employ.

**The central analytical problem Legion exists to solve** ("RPOs: Benevolent or Cruel
Intentions", the report's most important framing):
- Behaviour alone *cannot* distinguish a weapon from a surveillance asset - the same
 manoeuvre signature serves inspection, servicing, and attack.
- What resolves it: **capability + context + pattern-of-life**. "Knowledge that it has
 a grabber arm, or that it 'birthed' a smaller object near a US satellite, can help
 more fully assess purpose."
- → **This is Legion's reason to exist.** The compendium's job is to hold the
 capability + context + pattern-of-life that behaviour data alone lacks, so an analyst
 seeing a manoeuvre can look up what a thing is capable of, what it has done before,
 and what its class typically does next. The current app holds static attributes; the
 upgrade is the *intent-disambiguation* layer.

**Manoeuvre-signature tradecraft** (quantitative, the analyst keys off these):
- GEO station-keeping baseline: **0.5–1 m/s**. TJS-2 tracked at **44 m/s** - flagged
 precisely because it is ~44× the class baseline. *The anomaly is the deviation from
 the class baseline, not the absolute number* → Legion must hold the expected baseline
 per class so a deviation is legible.
- Operationally significant close approaches, verbatim from the report: TJS-10→TJS-3
 25 km; SY-24C→SJ-6-05A <1 km ("essentially face-to-face at ~17,000 mph");
 COSMOS-2581/2582 100 m; Luch/Olymp-2 <1 km from Intelsat 10-02.
- **Sun-Earth-Vehicle geometry as a tactic**: TJS-4 positioned itself between a US
 surveillance satellite and the Sun ("disadvantageous geometry for imaging") - a
 named, repeatable *technique*. Legion should catalogue tactics like this, not just
 objects.
- **"Dogfighting"**: a senior USSF official (March 2025) characterised the SY-24C/SJ-6
 corkscrew + sub-km RPO as "dogfighting" in LEO. Provenance the prior research JSON
 flagged as missing: speaker = senior USSF official; date = March 2025.

**The specific families cross-reference Legion's catalogue exactly** - TJS, SJ (SJ-21 =
the only confirmed noncooperative GEO capture, 2022; SJ-25 refuelling SJ-21), SY
(SY-12-01/02 belt-drifting inspectors; SY-24C "dogfighting" triad), Shenlong; and on the
Russian side the Nivelir co-orbital line (COSMOS-2576/USA-314, COSMOS-2558/USA-326), the
2025 COSMOS-2581/2/3 cluster, the Luch/Olymp SIGINT loiterers, COSMOS-2553
(nuclear-ASAT-related testbed, tumbling since ~Nov 2024). Full extraction with figures:
`research/02_domain_counterspace.md`.

**Corroborating / current sources:**
- **Secure World Foundation *Global Counterspace Capabilities* 2025/2026** (Samson,
 Cesari) - the parallel open-source assessment; five categories (direct-ascent,
 co-orbital, EW, directed energy, cyber). Cites a **USSF HQ Space Intelligence "Space
 Threat Fact Sheet" (21 Feb 2025)** giving the exact "dogfighting" detail (RPOs
 mid-March–end-April 2024, at times <1 km, "two simultaneous proximity events").
- **2026 currency** (SpaceNews / NASASpaceFlight / china-in-space.com): SJ-25 refuelled
 SJ-21 in GEO late 2025; the two separated mid-January 2026 (within 2 km 7–8 times
 1–15 Jan, then in-track burns to ~130 km apart, SJ-25 separating ~50 km/day). A **USSF
 fact sheet (July 2026)** again flags both China and Russia developing counterspace
 capabilities. → The compendium must be *current-events-aware*: entries are living, and
 the SJ-21/25 saga shows why a static catalogue is obsolete on arrival.

---

## 3. SDA analyst tradecraft and the pattern-of-life model

Sources: Aptima/AFRL *Probabilistic Satellite Maneuver Prediction*; MIT ARCLab GEO
Pattern-of-Life; Siew et al. *AI SSA Challenge* (AMOS 2023); Bicknell/Szymanski *Space
Object Pattern of Life Process Analysis*; LeoLabs *Analytic Space Domain Awareness*
(AMOS 2023).

**The paradigm shift that defines the modern analyst's work:** from **detect → track →
characterize → catalog** (object in isolation) to **activity-based / pattern-of-life
analysis** (the satellite's activities, relationships, and intent over time), borrowed
explicitly from GEOINT tradecraft. The three questions an analyst needs answered
(Aptima, verbatim): **where an object will be, its intent, and what relationships it has
to other objects.** Legion currently answers a weak "where" and nothing structured on
intent or relationships - those become first-class.

**The formal PoL data model (directly implementable):** a satellite's pattern-of-life =
**nodes + behavioural modes** (Siew et al.). A *node* is an instantaneous mode-change
point; a *behavioural mode* is a sustained regime between two nodes (station-keeping,
drift, RPO, pursuit, retirement). → Legion should model each object's history as a
sequence of `(mode, start_node, end_node)` segments. The existing charts already plot
raw element-set history; overlaying detected mode-change nodes turns a line graph into a
PoL timeline. This is Attack Flow's sequence idea, grounded in a real SDA model.

**Behavioural-mode vocabulary** (the controlled list for Legion): station-keeping,
longitudinal drift, RPO (inspection / shadowing / corkscrew / docking), pursuit /
co-planar shadowing, retirement/graveyard, separation/birthing, anomalous/high-Δv. Full
definitions: `research/03_sda_tradecraft.md`.

**Relative orbital elements (ROE)** are the right frame for proximity - analysts infer
RPO from *relative* motion (radial/along-track/cross-track), not two absolute tracks.
Legion's charts plot absolute mean longitude / mean motion; a relative-motion view
between a threat object and its named target is a significant upgrade (and aligns with
PSIRENS' co-planar view and ENLIGHTENMENT's relative-motion panels).

**Revisit rate / coverage as an honesty layer:** a manoeuvre characterisation is only as
good as the revisit rate (LeoLabs: 7–8 passes/day for a LEO pair; a sparse track can
miss a manoeuvre entirely). → Each object/behaviour carries a confidence reflecting *how
well we can actually see it*. Aligns with CONTEXT-001's existing rank-gate honesty ("a
wrong line is worse than a missing one").

---

## 4. Operational UI/UX and the ontology-graph paradigm

Sources: Palantir Gotham platform analyses (battlepolicy.com, softwareone, the dynamic-
ontology papers); the open "AEGIS / Gotham-like" implementation; and convergent 2025–26
dashboard-design references (UXPin, NN/g-cited, Fuselab, UK Data Service).

**The defining idea of elite intelligence tools: ontology + graph.** Stated bluntly
across every source - *"the most dangerous threats hide in the relationships between
things you have already seen."* Gotham's power is (1) an **ontology** - a formal model of
entity types and relationship types ("the instruction manual"), (2) the **graph** - 
entities connected and navigable ("the seeing stone"), and (3) propagating security.
→ **The central architectural upgrade for Legion: move from a flat catalogue to an
ontology of the threat domain.** Entity types: Object, Family/Programme,
Behaviour/Tactic, Event (manoeuvre / separation / close approach), Target, Nation/
Operator, Source. Relationship types: belongs-to-family, coplanar-with, shadowed,
birthed, approached, demonstrated-tactic, threatens, sourced-from. The analyst's core
question is a *graph traversal*, not a row lookup. This does **not** mean deploying a
graph database - for ~49 objects the graph lives in the JSON store as an adjacency
structure and renders client-side. The point is the *model and navigation*, not the
engine. Legion's existing family grouping is the embryonic form.

**Legion is an analytical + reference tool with an operational edge** - not a real-time
monitoring wall. Design for drill-down and comparison, not an always-on alert firehose.

**Convergent UI/UX principles** (all sources agree): five-second rule + inverted
pyramid; **progressive disclosure is *the* pattern** for data-dense tools (NN/g: cuts
cognitive load ~55%); functional minimalism (striking = restraint + hierarchy +
purposeful colour, never decoration); accessibility as a design multiplier (Section
508/WCAG discipline "tests better with all users"); **empty/error states as onboarding
moments** (the exact lesson of the failed research JSON and CONTEXT-001's recurring
"message that names something it cannot see" bug - the honest, specific, actionable
empty state is an operational feature); keyboard-driven operation + command palette for
a daily expert tool; sub-3-second load with progressive rendering.

**Visually striking, done right for *this* tool:** the dark operational theme (existing
Bluestaq house palette + validated 8-slot CVD-safe dataviz set) is correct for a
low-light console over long sessions - keep and systematise. The striking-ness comes
from a genuinely legible hierarchy, a **pattern-of-life timeline** as a signature visual
(nodes + modes, not a plain line), a **relationship graph** as a second signature
visual, and **provenance made visible** (colour + icon + label, never colour alone) so
the analyst *sees* the epistemic status of every claim. Foregrounding provenance as a
design element is Legion's distinctive - nobody else's tool does it, and it is directly
downstream of the house FACT/INFERENCE/SPECULATION rule. Reserve the copper-amber for
documents (house rule); the in-product attention accent is a chart-safe bright.

Full detail: `research/04_ui_ux_and_ontology.md`.

---

## 5. The single-sentence synthesis that drives the whole build

The best threat compendium is **an empirically-grounded, provenance-first ontology of
the threat domain** - objects, families, behaviours, events and their relationships - 
that lets an analyst move from *"what is this object doing right now"* to *"what is it
capable of, what has it done before, what is it related to, and how sure are we"* in a
few keystrokes, at a console, in the dark, faster than they could by opening seven other
tools. Legion today is a flat catalogue with a CRUD form and good charts. The upgrade is
to make **intent, relationships, behavioural history, and provenance** first-class,
without losing the disciplined, tested, shipped engineering that already clears the App
Store gate.
