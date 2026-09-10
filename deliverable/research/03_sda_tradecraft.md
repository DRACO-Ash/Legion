# Research strand 3: SDA analyst tradecraft & the pattern-of-life model

## The paradigm shift that defines the modern analyst's work
Sources: Aptima / AFRL "Probabilistic Satellite Maneuver Prediction"; MIT ARCLab
GEO Pattern-of-Life work; Siew et al. AI SSA Challenge (AMOS 2023); Bicknell/Szymanski
"Space Object Pattern of Life Process Analysis".

**The old model: detect → track → characterize → catalog.** Treats each object in
isolation. Cannot keep pace with thousands of objects; tells you WHERE something is, not
WHAT IT IS DOING or WHY.

**The new model: activity-based / pattern-of-life (PoL) analysis, borrowed explicitly
from GEOINT tradecraft.** Analyses "the activities or patterns of life the satellite is
engaging in, rather than focusing on the satellite in isolation." The three questions an
analyst actually needs answered (Aptima, verbatim): **where an object will be in the
future, its intent, and what relationships it has to other space objects.**
→ Legion's entire value proposition maps onto these three. The current app answers a
weak version of "where" (charts) and nothing structured on intent or relationships. The
upgrade is to make INTENT and RELATIONSHIPS first-class.

## The formal PoL data model (directly implementable in Legion)
From Siew et al. (AMOS 2023), the canonical structure:
- A satellite's Pattern-of-Life = **nodes** + **behavioural modes**.
- A **node** is an instantaneous point on the PoL timeline that SEPARATES two distinct
 behavioural modes (a "mode change" - e.g. station-keeping → drift, or the onset of an
 RPO approach).
- A **behavioural mode** is a sustained regime between two nodes (station-keeping,
 longitudinal drift, RPO/rendezvous, pursuit, retirement/graveyard).
→ This is a clean, well-founded schema. Legion should model each threat object's history
as a sequence of (mode, start-node, end-node) segments. The existing charts already plot
the raw element-set history; overlaying detected mode-change nodes turns a line graph
into a PoL timeline an analyst can read at a glance. This is the "engagement timeline"
concept from Attack Flow, grounded in a real SDA data model.

## Behavioural modes / manoeuvre vocabulary the analyst uses
Synthesised from the maneuver-detection and RPO literature:
- **Station-keeping**: small periodic corrections holding a slot. GEO baseline 0.5-1 m/s.
 Propulsion type (chemical / electric / hybrid) is itself a characterization feature
 (electric = small, long-duration, finer control; chemical = larger impulsive burns).
- **Longitudinal drift** (GEO): abandoning a slot to walk the belt at a steady deg/day.
 Direction + rate + turnaround points are the signature (cf. SY-12-01/02).
- **Rendezvous & proximity operations (RPO)**: closing on another object. Sub-classes:
 inspection, shadowing/co-planar station-keeping, corkscrew/walking approach, docking.
- **Pursuit / co-planar shadowing**: matching a target's plane and loitering (the
 COSMOS-2576/USA-314 pattern).
- **Retirement / graveyard**: raising out of GEO (+300 km super-synchronous).
- **Separation / birthing event**: releasing a sub-object (Shenlong, TJS-3 subsat,
 Nivelir matryoshka). A named node type of high analytic significance.
- **Anomalous / high-delta-v**: manoeuvre far outside the class baseline (TJS-2 at 44 m/s).

## Relative orbital elements (ROE) - the right frame for proximity
Maneuver detection "typically leverages relative orbital element (ROE) analysis, nodal
element parameterizations, or angles-only tracking to infer proximity behaviors such as
station-keeping, rendezvous, or pursuit." → For any RPO between two objects, the
operationally meaningful view is the RELATIVE motion (radial / along-track / cross-track),
not two absolute tracks. Legion's charts currently plot absolute mean longitude / mean
motion; a relative-motion view between a threat object and its named target/coplanar
object would be a significant analyst upgrade (this is what PSIRENS' co-planar view and
the ENLIGHTENMENT "relative motion panels" already gesture at - the compendium should
link to / embed that framing).

## Revisit rate / sensor coverage as an honesty layer
LeoLabs "Analytic Space Domain Awareness" (AMOS 2023): a maneuver characterization is
only as good as the revisit rate (they cite 7-8 passes/day for a LEO pair). A sparse
track can miss a manoeuvre entirely.
→ Directly supports the "Summiting the Pyramid" coverage-honesty idea for Legion: each
object/behaviour should carry a confidence that reflects HOW WELL WE CAN ACTUALLY SEE IT
(sensor coverage, revisit, photometric availability). A compendium that silently presents
sparse and dense tracks identically misleads the analyst. This aligns with CONTEXT-001's
existing rank-gate honesty ("a wrong line is worse than a missing one").

## Confidence / provenance discipline (the intelligence-analysis standard)
This is house doctrine already (FACT / INFERENCE / SPECULATION), and it matches formal
intelligence tradecraft (ICD 203-style analytic standards: sourcing, confidence levels,
distinguishing underlying information from assessment). The compendium must carry, per
claim: (a) the assertion, (b) FACT/INFERENCE/SPECULATION, (c) a confidence level,
(d) a source with provider-class, (e) a date. The prior failed research JSON is itself a
case study in why: it honestly recorded "could not verify" rather than fabricating, and
that honesty is the feature, not the bug.
