# Research strand 2: The counterspace threat domain (analyst's operational picture)

## Primary source: CSIS Space Threat Assessment 2025 (Swope, Bingen, Young, LaFave, April 2025)
Full PDF read. This is THE authoritative open-source reference an orbital warfare
analyst uses. Eight years of continuous data. Key extractions below, all attributable
to this document (FACT at the level of "CSIS assessed this from open sources").

### The counterspace weapon taxonomy (Legion needs this as a classification spine)
Four top-level categories:
1. **Kinetic** - physical means. DA-ASAT missiles (ground-to-space), orbital ASAT
  (space-to-space projectile), orbital grappling satellites (grab + harm/move),
  terrestrial infrastructure attack. All permanent effect.
2. **Non-kinetic** - radiated energy. Directed (laser dazzlers, HPM) or distributed
  (nuclear detonation / EMP). Permanent to temporary.
3. **Electronic** - EM spectrum denial. Jamming, spoofing of GNSS/SATCOM. Temporary
  effect, reversible, not-permanent, limited/regional.
4. **Cyber** - offensive cyberspace ops against space systems (ground, terminal,
  spacecraft). Ambiguous intent, variable permanence.

Each weapon type has an axis-set CSIS uses to differentiate - these are DIRECTLY the
attributes Legion should carry per threat system:
- Origin→Destination (ground-to-ground / ground-to-space / space-to-space)
- Permanence of attack (permanent / not-permanent / varies)
- Scale of effect (limited-regional / widespread)
- Attributability (launch site attributable / trackable-orbit attributable / limited)
- Requires space launch capability (y/n)
- Requires space domain awareness to employ (y/n)

### The central analytical problem Legion exists to help solve
"RPOs: Benevolent or Cruel Intentions" section - the single most important framing:
- **Behaviour alone cannot distinguish a weapon from a surveillance asset.** The same
 manoeuvre signature serves inspection, servicing, and attack. A grappler that services
 is a grappler that can harm.
- What resolves the ambiguity: **capability + context + pattern-of-life.** "Knowledge
 about a satellite's capabilities and context - that it has a grabber arm, or that it
 'birthed' a smaller object near a US satellite - can help more fully assess purpose."
- → THIS IS LEGION'S REASON TO EXIST. The compendium's job is to hold the capability +
 context + pattern-of-life that behaviour data alone lacks, so an analyst seeing a
 manoeuvre can look up "what is this thing capable of, what has it done before, what
 does its class typically do next." The current app holds static attributes; the
 upgrade is to hold the INTENT-DISAMBIGUATION layer.

### Manoeuvre signatures - the quantitative tradecraft (analyst keys off these)
- Standard GEO station-keeping / repositioning: **0.5–1 m/s**.
- TJS-2 tracked manoeuvring at **44 m/s** - "unusually high", flagged specifically
 because it is ~44x normal and "uses significantly more fuel". → The anomaly is the
 DEVIATION from the class baseline, not the absolute number. Legion should hold the
 expected baseline per class so a deviation is legible.
- Close-approach distances that mattered operationally: TJS-10 to TJS-3 = 25 km;
 SY-24C to SJ-6-05A < 1 km ("essentially face-to-face for satellites at ~17,000 mph");
 COSMOS-2581/2582 = 100 m apart; COSMOS-2583 passed 0.5 km; Luch/Olymp-2 ~5 km from
 Thor 7, < 1 km from Intelsat 10-02.
- **Sun-Earth-Vehicle geometry as a tactic**: TJS-4 "maneuvered to position itself
 between a US space surveillance satellite and the Sun, creating a disadvantageous
 geometry for imaging" - i.e. hiding in the solar exclusion cone. This is a named,
 repeatable TACTIC (a "technique" in ATT&CK terms). Legion should catalogue tactics
 like this, not just objects.
- **"Dogfighting"**: March 2025, a senior Space Force official publicly characterised
 SY-24C / SJ-6 corkscrew + <1km RPO as "dogfighting" in LEO. This is the quotable
 provenance the prior research JSON flagged as missing - speaker: senior USSF official;
 timing: March 2025; behaviour: corkscrew manoeuvres + sub-km RPO.

### The specific families (cross-references Legion's catalogue exactly)
CHINA:
- **TJS** (Tongxin Jishu Shiyan, "communication technology test"), 17 satellites, GEO,
 suspected military early warning + SIGINT. TJS-3 is a suspected GEO inspector.
- **SJ (Shijian)**, 43 satellites, all regimes, "experimental". SJ-21 = the ONLY
 confirmed noncooperative capture in GEO (moved a defunct Beidou to graveyard, 2022).
 SJ-25 coplanar with SJ-21 Jan 2025, suspected refuelling. SJ-23 = GSSAP-analogue.
- **SY (Shiyan)**, 45 satellites, all regimes. SY-12-01/02 = paired GEO inspectors
 drifting opposite directions across the whole belt (turnaround points named:
 178.9°E Pacific, 17.3°E central Europe). SY-24C triad = the "dogfighting" LEO
 demonstrators doing corkscrews around SJ-6-05B.
- **Shenlong** spaceplane: released/manoeuvred-with/possibly-captured an object,
 260+ days on orbit, released 6 objects after Dec 2023 launch.

RUSSIA:
- **Nivelir line** (co-orbital inspectors, the "matryoshka" nesting-doll pattern):
 COSMOS-2576 coplanar with USA 314 (May 2024, raised orbit Feb 2025). COSMOS-2558
 coplanar with USA 326 (since Aug 2022). The 2019/2022 payloads had "characteristics
 resembling previously deployed counterspace payloads".
- **2025 cluster**: COSMOS-2581/2582/2583 (MoD-acknowledged), formation flying to 100m.
- **Luch/Olymp** SIGINT loiterers: Olymp-2 visited Eutelsat Konnect, RASCOM-QAF-1,
 Astra 4A, Thor 7/6, SES-5, Intelsat 3-F7/10-02. Olymp-1 parked near Intelsat 37e
 at 342°E then began 0.5°/day eastward drift March 2025. **Pattern-of-life is the
 signature**: a SIGINT loiterer parks near comms sats over regions of interest.
- **COSMOS-2553** (suspected nuclear-ASAT-related tech testbed): 2,000 km orbit, high
 radiation region, tumbling since ~Nov 2024 (LeoLabs radar) → likely non-operational.

### Doctrinal frameworks an analyst works within (for training/context modules)
- **DOD 5 tenets of responsible behaviour** (2021): due regard, limit long-lived debris,
 avoid harmful interference, safe separation/trajectory, communicate + notify.
- **USSPACECOM 8 specific behaviours** (Feb 2023) mapping to those tenets.
- These define the "norms" baseline against which adversary behaviour is judged
 irresponsible/escalatory. A compendium module on "norms vs. observed deviance" has
 direct operational use for the analyst writing up why a behaviour matters.

### Provider ecosystem an analyst actually consumes (the sourcing reality)
Named commercial SSA sources CSIS itself relies on and credits: COMSPOC, ExoAnalytic,
Integrity ISR, LSAS Tec, s2a systems, Slingshot Aerospace, LeoLabs, HEO. Government:
GSSAP, Space-Track (USSPACECOM), Vimpel catalogue (Russia), ISON (Russia-led optical).
→ Legion sits downstream of exactly this ecosystem; UDL aggregates much of it. The
compendium's provenance field should be able to name which provider-class a claim came
from, because analysts weight sources differently (a LeoLabs radar tumbling call is
harder evidence than a social-media close-approach graphic).
