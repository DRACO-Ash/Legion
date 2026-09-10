# LEGION COMPENDIUM - Content Seed (sourced, provenance-carried)

**What this is.** The initial domain content to load into the ontology, drawn from the
open-source assessments researched for this specification, every item carrying its
source. This is a *starting seed*, not a finished intelligence product. It is drafted to
the FACT/INFERENCE/SPECULATION standard so it can be loaded as `Claim`-carrying records.

**Critical honesty note - read before loading.** The prior research file
(`legionfamilyresearchUNVERIFIED.json`) returned almost empty because its verification
step could not open sources. This seed is different: every claim below cites a source
that *was* opened and read during this research session (principally the CSIS Space
Threat Assessment 2025 full PDF, plus corroborating search-surfaced reporting). BUT:
- Claims sourced only to a single document should load with `confidence: moderate`, not
 `high`, until corroborated by a second independently-read source.
- Claims marked INFERENCE or SPECULATION below must load with those markers, not be
 silently promoted.
- **[DECISION - Ash] §3 applies:** a role-holder should validate each family assessment
 before it is treated as authoritative (`validated_by`). Load with `validated_by = None`
 and the "awaiting validation" banner until then.
- Do not add a claim to this seed that was not actually sourced. If a field is unknown,
 it is a `tbc` claim with a named owner, not a guess.

**Source key (map to `SourceClass`):**
- CSIS-STA-2025 = CSIS *Space Threat Assessment 2025* (Swope, Bingen, Young, LaFave,
 April 2025). `source_class: think_tank`. Full report read this session.
- SWF-GCC-2025 = Secure World Foundation *Global Counterspace Capabilities* 2025
 (Samson, Cesari). `source_class: think_tank`. Search-surfaced this session.
- USSF-FS-2025 = USSF HQ Space Intelligence "Space Threat Fact Sheet", 21 Feb 2025
 (cited by SWF/Breaking Defense). `source_class: official_gov`. Secondary citation - 
 mark INFERENCE unless the primary is obtained.
- USSF-official-Mar2025 = senior USSF official "dogfighting" characterisation, March
 2025 (CSIS-STA-2025 and press). `source_class: official_gov`.
- CIS-2026 = china-in-space.com SJ-25/SJ-21 separation reporting, Jan 2026.
 `source_class: press`.
- Existing Legion catalogue = the 49 seeded systems already in `src/seed_data.py`,
 mirrored from `Red_ASAT_Systems.xlsx`. `source_class: internal_assessment` / existing.

---

## 1. Tactics (the ATT&CK-technique analogue) - seed set

Each loads as a `Tactic` with a `description_claim` and an `observable`.

1. **Co-planar shadowing** (`enabling` / `non_kinetic` posture).
  Matching a target's orbital plane and loitering to observe or hold at risk.
  Observable: sustained near-zero relative plane separation with a friendly/allied
  asset. Source: CSIS-STA-2025 (COSMOS-2576/USA-314, COSMOS-2558/USA-326). FACT,
  moderate.

2. **Solar-exclusion positioning** (`non_kinetic` enabling).
  Manoeuvring to sit between a surveilling satellite and the Sun, creating a
  disadvantageous imaging geometry (hiding in the solar exclusion cone).
  Observable: object positions on the Sun-line relative to a known imager.
  Source: CSIS-STA-2025 (TJS-4). FACT, moderate.

3. **Corkscrew / walking RPO ("dogfighting")** (`enabling`, potential `kinetic`).
  Close, repeated, manoeuvring proximity operations around a target, at times sub-km.
  Observable: rapid relative-motion changes, multiple simultaneous proximity events.
  Source: USSF-official-Mar2025; USSF-FS-2025 (RPOs mid-Mar–end-Apr 2024, <1 km, "two
  simultaneous proximity events"). FACT (characterisation), moderate. The specific USSF
  fact-sheet wording is a secondary citation → mark the sub-km detail INFERENCE until
  the primary fact sheet is obtained.

4. **SIGINT loiter near comms asset** (`electronic`/`enabling`).
  Parking a collection satellite near a commercial/allied comms satellite over a region
  of interest. Observable: repeated station-keeping adjacent to comms sats over
  specific longitudes. Source: CSIS-STA-2025 (Luch/Olymp near Thor, Intelsat, Astra,
  SES). FACT, moderate.

5. **Sub-object release / birthing (matryoshka)** (`enabling`, potential `kinetic`).
  Releasing a smaller object from a parent, near a target or for later use.
  Observable: a new catalogued object originating at a parent's position.
  Source: CSIS-STA-2025 (Shenlong released objects; Nivelir nesting; TJS-3 subsat).
  FACT, moderate.

6. **Noncooperative capture / grappling** (`kinetic`).
  Physically taking hold of an uncooperative object and moving it.
  Observable: docking-range approach followed by a coordinated orbit change of both.
  Source: CSIS-STA-2025 (SJ-21 towed a defunct Beidou to graveyard, 2022 - the only
  confirmed GEO instance). FACT, high (this one is well-corroborated and explicitly
  called the only confirmed instance).

7. **High-Δv repositioning (fuel-without-regret)** (`enabling`).
  Manoeuvring far in excess of the class baseline, signalling operational proficiency
  and willingness to expend fuel. Observable: a manoeuvre Δv many multiples of the
  class station-keeping baseline. Source: CSIS-STA-2025 (TJS-2 at 44 m/s vs 0.5–1 m/s
  baseline). FACT, moderate.

---

## 2. Targets - seed set (the threatened assets referenced by the catalogue)

Load as `Target` records so the "coplanar_with" / "shadowed" edges have an endpoint.
All sourced to CSIS-STA-2025 unless noted. FACT, moderate.
- USA 314 (US Government, SDA-related) - shadowed by COSMOS-2576.
- USA 326 (US Government) - shadowed by COSMOS-2558.
- Intelsat 10-02 (Intelsat, comms/broadcast) - approached by Luch/Olymp-2 (<1 km, Jan
 2025).
- Thor 7 (comms/broadcast) - approached by Luch/Olymp-2 (~5 km, Jul 2024).
- Astra 4A, RASCOM-QAF-1, SES-5, Intelsat 3-F7, Thor 6, Eutelsat Konnect - Luch/Olymp-2
 loiter set.
- Intelsat 37e - Luch/Olymp-1 parked near (342°E) then drifted, Mar 2025.
- A defunct Beidou (PRC) - captured/towed by SJ-21 (2022).
- SJ-21 itself is both a red-catalogue object AND the target of SJ-25's refuelling - model
 the refuelling edge object→object.

---

## 3. Family assessments - seed drafts

Draft `FamilyAssessment` records for the existing families. Each loads with
`validated_by = None` (awaiting role-holder validation, per house rule). Only the
highest-confidence exemplars are drafted here in full; the implementer extends the
pattern to the remaining families using the same sourcing discipline, and marks anything
unknown as a `tbc` claim with owner "Ash / JCO SME", never a guess.

### SJ (Shijian) - GEO servicing / RPO
- **one_line** (FACT, moderate; CSIS-STA-2025): China's GEO on-orbit servicing and RPO
 line, dual-use - the same capabilities that service can harm.
- **role_summary** (FACT, moderate; CSIS-STA-2025): experimental on-orbit servicing,
 inspection, refuelling and capture demonstrations in GEO.
- **manoeuvre_baseline**: GEO station-keeping 0.5–1 m/s (FACT, moderate; CSIS-STA-2025).
- **what_raises_concern** (each a claim):
 - SJ-21 conducted the only confirmed noncooperative capture in GEO (Beidou tow, 2022).
  FACT, high; CSIS-STA-2025.
 - SJ-25 entered coplanar orbit with SJ-21 (Jan 2025) and refuelled it (late 2025);
  the pair separated mid-Jan 2026 at ~50 km/day. FACT, moderate; CSIS-STA-2025 +
  CIS-2026.
 - TJS-3 moved within 1° latitude of SJ-21 (Jan 2025), a possible supporting role.
  INFERENCE, moderate; CSIS-STA-2025.
- **capabilities**: robotic_arm (SJ-17/SJ-21), noncooperative_capture (SJ-21),
 refuelling (SJ-25↔SJ-21), inspection_rpo. Each a sourced claim.
- **open_questions**: exact payload of each SJ variant; whether SJ-23/SJ-28 are inspectors
 or servicers; the next SJ-25 target. (Load as plain open-question strings.)

### SY (Shiyan) - inspectors + "dogfighting" demonstrators
- **one_line** (FACT, moderate; CSIS-STA-2025): China's experimental inspection line
 spanning GEO belt-drifting pairs and LEO close-proximity "dogfighting" triads.
- **manoeuvre_baseline**: varies by sub-series; GEO pair drift across the belt with
 turnaround points; LEO triad sub-km RPO.
- **what_raises_concern**:
 - SY-12-01/02 drift the entire GEO belt in opposite directions (turnarounds 178.9°E,
  17.3°E). FACT, moderate; CSIS-STA-2025.
 - SY-24C triad conducted corkscrew RPO around SJ-6-05B and sub-km RPO with SJ-6-05A
  (<1 km, Apr 2024), characterised by a senior USSF official as "dogfighting". FACT
  (characterisation), moderate; CSIS-STA-2025 + USSF-official-Mar2025.
- **capabilities**: inspection_rpo, coplanar_shadowing (SY-12 vs USA 270),
 sub_object_release, high_delta_v_manoeuvre. Sourced claims.

### TJS (Tongxin Jishu Shiyan) - GEO SIGINT / early warning + inspection
- **one_line** (FACT, moderate; CSIS-STA-2025): suspected military early-warning and
 SIGINT GEO line, several members demonstrating inspection and evasive geometry.
- **what_raises_concern**:
 - TJS-4 used solar-exclusion positioning against a US surveillance satellite. FACT,
  moderate; CSIS-STA-2025.
 - TJS-2 manoeuvred at 44 m/s (≈44× baseline). FACT, moderate; CSIS-STA-2025.
 - TJS-10 closed to 25 km of TJS-3 (May 2024). FACT, moderate; CSIS-STA-2025.
- **capabilities**: sigint_payload, inspection_rpo, high_delta_v_manoeuvre,
 solar-exclusion (as demonstrated_tactic edge).

### Nivelir line (Russia) - co-orbital inspectors / matryoshka
- **one_line** (FACT, moderate; CSIS-STA-2025): Russia's co-orbital inspector line, a
 nesting-doll release pattern, several members co-planar with US assets and assessed as
 counterspace weapons by USSF.
- **what_raises_concern**:
 - COSMOS-2576 entered coplanar orbit with USA 314 (May 2024). FACT, moderate;
  CSIS-STA-2025.
 - COSMOS-2558 coplanar with USA 326 since Aug 2022. FACT, moderate; CSIS-STA-2025.
 - The 2019/2022 payloads had "characteristics resembling previously deployed
  counterspace payloads" (US assessment). FACT (of the assessment), moderate;
  CSIS-STA-2025.
- **capabilities**: coplanar_shadowing, sub_object_release, kinetic_kill_vehicle
 (assessed for the line's KKV members - mark INFERENCE where not confirmed per object).

### Luch / Olymp (Russia) - GEO SIGINT loiterers
- **one_line** (FACT, moderate; CSIS-STA-2025): Russia's GEO SIGINT loiter line, parking
 near commercial/allied comms satellites over regions of interest.
- **what_raises_concern**: the loiter target set over Europe/Africa/Middle East (see §2);
 the correlation of Olymp-2 arriving near Astra 4A with ground jamming of Ukrainian
 broadcasts (INFERENCE on the causal link - CSIS explicitly says "not clear", so mark
 it SPECULATION on causality, FACT on co-occurrence).
- **capabilities**: sigint_payload, coplanar_shadowing (loiter form).

### 2026 Russian manoeuvrable cluster + the NORAD-68762 clash
- The existing catalogue flags COSMOS-2612/2613/2614 sharing NORAD 68762 as a suspected
 transcription error to cross-check against UDL (existing Legion flag). Load this as an
 `open_question` with owner "Ash - cross-check UDL", NOT as a resolved fact. This is
 itself a worked example of the provenance discipline: a known data-quality flag,
 carried honestly, with the owner named.

---

## 4. Behaviour events - seed set (dateable, citable, graph-edge-bearing)

Load as `BehaviourEvent` records (each drives a graph edge and a PoL node). All
CSIS-STA-2025 unless noted, FACT/moderate:
- 2022 - SJ-21 capture+tow of defunct Beidou to graveyard (capture). high confidence.
- 16 May 2024 - TJS-10 within 25 km of TJS-3 (close_approach, 25 km).
- Apr 2024 - SY-24C ↔ SJ-6-05A <1 km (close_approach, <1 km).
- May 2024 - COSMOS-2576 enters coplanar with USA 314 (plane_change/shadowing onset).
- 5 Mar 2025 - COSMOS-2581/2582 100 m apart (close_approach, 0.1 km).
- 7 Mar 2025 - COSMOS-2583 passes 0.5 km to COSMOS-2581/2582 (close_approach, 0.5 km).
- Jul 2024 - Luch/Olymp-2 ~5 km from Thor 7 (close_approach, 5 km).
- Jan 2025 - Luch/Olymp-2 <1 km from Intelsat 10-02 (close_approach, <1 km).
- Jan 2025 - SJ-25 coplanar with SJ-21 (plane_change/shadowing onset).
- Late 2025 - SJ-25 refuels SJ-21 (refuelling). CIS-2026 + CSIS-STA-2025.
- 1–15 Jan 2026 - SJ-25/SJ-21 within 2 km 7–8 times (close_approach series). CIS-2026.
- 16 Jan 2026 - SJ-25/SJ-21 in-track burns, separate to ~130 km, ~50 km/day
 (manoeuvre/plane_change). CIS-2026.

---

## 5. Loading procedure (for the implementer)

1. Load tactics (§1), targets (§2), and family assessments (§3) first - they are
  referenced by edges and events.
2. Load behaviour events (§4), linking `primary_object_id` to the existing catalogue
  objects by matching `catalogue_name`/`norad_id`, and `counterpart_*` to targets or
  objects.
3. Derive the relationship edges from the events and the assessments (a close_approach
  event → an `approached` edge; a capture → a `captured` edge; a family membership →
  `belongs_to_family`; a demonstrated tactic → `demonstrated_tactic`).
4. Every record loads with its `Claim` provenance from the source key above. Nothing
  loads as bare fact.
5. Run the migration idempotently; assert the 49 existing systems are untouched and the
  new content is present.
6. **Do not** mark any family assessment `validated_by` until [DECISION - Ash] §3 gives
  the validation route. They render "awaiting validation" until then.

**Provenance self-check before shipping the seed** (the failed-JSON test):
- [ ] Does every seeded claim cite a source that was actually read? → must be yes.
- [ ] Is every single-source claim loaded at `moderate`, not `high`? → must be yes,
   except the explicitly well-corroborated SJ-21 capture.
- [ ] Is every INFERENCE/SPECULATION loaded with its marker, not promoted? → must be yes.
- [ ] Is every unknown a `tbc` claim with a named owner, not a guess? → must be yes.
- [ ] Are the family assessments all `validated_by = None` pending Ash's route? → yes.
