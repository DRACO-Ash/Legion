# Research strand 1: How the best threat/tactics knowledge bases actually work

## The reference standard: MITRE ATT&CK (Strom et al., Design & Philosophy, 2018/2020)

Source: mitre.org ATT&CK Design and Philosophy paper (Blake Strom, Andy Applebaum et al.),
and the ATT&CK for ICS Philosophy paper (2020).

### Why ATT&CK works - the transferable design principles

1. **Mid-level abstraction is the whole game.** ATT&CK deliberately sits between
  high-level conceptual models (the Cyber Kill Chain: linear, 7 stages, too abstract
  to action) and low-level databases (exploit/CVE/malware-hash: too specific to
  generalise). The mid level is "specific enough to relate an adversary action to a
  specific way of defending against it, general enough to span many concrete cases."
  → For Legion: a threat SYSTEM entry must sit at the level where an analyst can act
  on it - not just "COSMOS-2519 exists" (too low) and not "Russia does co-orbital
  RPO" (too high), but "this class of inspector manoeuvres to a co-planar shadowing
  position, and here is the observable that tells you it is happening."

2. **A common taxonomy understood by BOTH offence and defence.** ATT&CK's tactics are
  the adversary's GOALS (why); techniques are the METHODS (how); procedures are the
  specific in-the-wild executions. The same vocabulary serves the red team emulating
  and the blue team detecting.
  → For Legion: the compendium needs a shared vocabulary spanning the threat behaviour
  (what the red satellite does) AND the analyst's response (what the JCO operator
  watches for, reports, and does about it). One vocabulary, both sides.

3. **Empirically grounded, never speculative.** Every ATT&CK technique is backed by
  real observed adversary use, with citations. "ATT&CK is not an exhaustive
  enumeration of attack vectors" - it is a curated record of what has actually been
  seen. Circumstantial evidence of use is explicitly flagged as such.
  → For Legion this maps EXACTLY onto Ash's FACT / INFERENCE / SPECULATION discipline.
  Every claim in the compendium carries a provenance marker and a source. This is
  already the house rule; the compendium format must enforce it structurally.

4. **Consistent abstraction across entries (the sub-technique reform).** ATT&CK's 2020
  sub-technique restructure existed to make the abstraction level UNIFORM across the
  whole base - some "techniques" had drifted more specific than others, which broke
  comparability. Sub-techniques have exactly one parent (no many-to-many) to keep the
  model maintainable.
  → For Legion: every threat-system family entry must be filled to the same depth and
  shape, or cross-family comparison (the analyst's core task) silently breaks. A
  schema with required fields enforces this. The current app's free-text `notes`
  field does NOT.

5. **Structured for multiple driving use cases at once.** ATT&CK was built to serve
  intrusion detection, threat hunting, red teaming, adversary emulation, and defensive
  gap measurement simultaneously - the structure had to serve all of them. The
  "driving use cases" were foundational, decided up front.
  → For Legion the driving use cases (decide these up front): (a) rapid threat
  characterisation during a live event, (b) training a new Space Event Analyst,
  (c) pattern-of-life baseline vs. current behaviour, (d) cross-system comparison
  ("which of these has demonstrated a kinetic capability?"), (e) briefing generation.

### Adjacent CTID projects worth stealing conceptually

- **Attack Flow** (2022, updated 2026): captures the ENTIRE SCOPE of an attack as a
 sequence of actions + conditions + assets, not isolated techniques. "Defenders think
 in lists, adversaries think in graphs." The sequence/graph is the unit, not the
 single technique.
 → For Legion: a threat satellite's behaviour is a SEQUENCE - launch → commissioning →
 drift to station → co-planar approach → shadowing → (separation event) → return.
 Modelling the sequence, not just static attributes, is the single biggest conceptual
 upgrade available. An "engagement timeline" / behaviour-sequence view.

- **Summiting the Pyramid** (2026): measures the DEPTH and QUALITY of detection
 coverage, not just presence/absence on a heatmap. Moves beyond a binary "we cover
 this technique" to "how robustly."
 → For Legion: a coverage/confidence view - for each threat behaviour, how well can we
 actually observe it? (sensor coverage, photometric availability, revisit rate). This
 is the analyst's honesty layer: what we can and cannot see.

- **The Pyramid of Pain** (David Bianco, the intellectual ancestor): ranks indicators
 by how much it costs the adversary when you deny them - hash values (trivial to
 change) at the bottom, TTPs (expensive to change) at the top. The higher up you
 detect, the more it hurts.
 → For Legion: an analyst wants to key off the things the adversary CANNOT easily
 change - orbital mechanics, manoeuvre signatures, hardware constraints (seeker
 lighting) - not the things they can (naming, cover stories). Structuring the
 compendium around durable observables is directly analogous.

## The US Army milWiki precedent (2009)

Source: army.mil article 23722.

The US Army Combined Arms Center ran a milWiki test to let soldiers revise TTPs in real
time via a wiki, because the field-manual update cycle was 3-5 YEARS and could not keep
pace with a fast-changing field. Governance model: editing rules requiring
authentication and expertise, "similar to Wikipedia." Purpose: fill the gap between
what students learn at the schoolhouse and practical application in a fast-moving field.

Transferable lessons:
- The doctrinal-update-cycle problem is real and central: a threat compendium that can
 only be updated slowly is obsolete on arrival. The satellite threat picture changes
 faster than any document-review cycle. → live, editable, versioned data (Legion
 already does this with the JSON store - this validates the architecture choice).
- Governance matters: who can edit, and how is authority/expertise represented. Legion
 removed auth entirely (platform-fronted). The compendium needs an EDITORIAL layer - 
 provenance and "who asserted this / how sure are we" - even without login auth. That
 is the analyst-facing equivalent of edit governance.
- The schoolhouse-to-field gap is a named, funded problem. A compendium that doubles as
 a TRAINING instrument (not just a reference) addresses a real operational need. This
 is why the ENLIGHTENMENT trainer and this compendium are complementary.
