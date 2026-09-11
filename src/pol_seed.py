"""Seeded pattern-of-life segments, drawn from the research.

Why seed any at all: an empty timeline demonstrates nothing, and the Phase 3
bar is that selecting an object shows its behavioural history. These are the
behaviours the research describes, turned into the controlled vocabulary,
each carrying the claim that sources it.

Three things govern every entry here.

● **The epoch is only as precise as the source.** The research says "May
  2024", not a day, so the segment says `2024-05`. Writing `2024-05-01`
  would invent a date, and a timeline that draws it as the first of the month
  is asserting something nobody observed. `parse_pol_epoch` handles year,
  month and day precision, and the interface says which it has.
● **A counterpart is a catalogue name where the object is catalogued, and a
  `target:` slug where it is not.** USA 314 is not one of our systems, and
  pretending otherwise would put a phantom row in the catalogue. The slug
  says plainly that the counterpart is outside it, and Phase 5's `Target`
  records are where those become first-class.
● **Every segment carries a real claim.** Marker, confidence, source class,
  citation and who asserted it, validated like any other. A segment is an
  assessment, not an observation, and the timeline must never read as
  telemetry.
"""

from typing import Any

TARGET_PREFIX = "target:"

CSIS_2025 = "CSIS Space Threat Assessment 2025 (Swope, Bingen, Young, LaFave)"
ASSERTED_BY = "seed-loader, from deliverable/research/02_domain_counterspace.md"
THINK_TANK = "think_tank"


def _claim(statement: str, marker: str = "FACT", confidence: str = "moderate") -> dict:
    return {
        "statement": statement,
        "marker": marker,
        "confidence": confidence,
        "source_class": THINK_TANK,
        "source_citation": CSIS_2025,
        "asserted_by": ASSERTED_BY,
    }


def _segment(
    seed_key: str,
    object_name: str,
    mode: str,
    start_epoch: str,
    statement: str,
    *,
    end_epoch: str | None = None,
    related_name: str | None = None,
    observability: str = "unknown",
    marker: str = "FACT",
    confidence: str = "moderate",
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "seed_key": seed_key,
        "object_name": object_name,
        "related_name": related_name,
        "mode": mode,
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "observability": observability,
        "notes": notes,
        "claim": _claim(statement, marker, confidence),
    }


SEED_SEGMENTS: list[dict[str, Any]] = [
    # --- the confirmed capture, and the pair the build spec names ----------
    _segment(
        "sj21-capture-2022",
        "SJ-21",
        "rpo_docking",
        "2022",
        "SJ-21 conducted the only confirmed noncooperative capture in GEO, "
        "moving a defunct Beidou satellite to a graveyard orbit in 2022.",
        related_name=f"{TARGET_PREFIX}beidou-defunct",
        confidence="high",
        notes="The single most cited capability demonstration in this catalogue.",
    ),
    _segment(
        "sj25-sj21-coplanar-2025",
        "SJ-25",
        "rpo_shadowing",
        "2025-01",
        "SJ-25 became coplanar with SJ-21 in January 2025, assessed as a "
        "suspected refuelling operation.",
        related_name="SJ-21",
        notes="Suspected refuelling is the assessment, coplanarity is the observation.",
    ),
    _segment(
        "sj21-sj25-coplanar-2025",
        "SJ-21",
        "rpo_shadowing",
        "2025-01",
        "SJ-21 was the counterpart of SJ-25's January 2025 coplanar "
        "operation, assessed as suspected refuelling.",
        related_name="SJ-25",
    ),
    # --- the dogfighting triad, and the objects they flew around -----------
    *[
        _segment(
            f"sy24c-{index}-corkscrew-2025",
            name,
            "rpo_corkscrew",
            "2025-03",
            "A senior US Space Force official publicly characterised the "
            "SY-24C triad's corkscrew manoeuvres and sub-kilometre RPO "
            "against SJ-6 as dogfighting in LEO, in March 2025.",
            related_name="SJ-6-05B",
            confidence="high",
        )
        for index, name in enumerate(
            ["SHIYAN 24C 01", "SHIYAN 24C 02", "SHIYAN 24C 03"], start=1
        )
    ],
    _segment(
        "sj6-05a-close-pass-2025",
        "SJ-6-05A",
        "rpo_inspection",
        "2025-03",
        "SY-24C closed to under 1 km of SJ-6-05A, described as essentially "
        "face to face for satellites travelling at about 17,000 mph.",
        related_name="SHIYAN 24C 01",
        notes="Which SJ-6 object was which is part of what needs verifying.",
    ),
    # --- the Nivelir shadows of US assets ----------------------------------
    _segment(
        "cosmos2576-usa314-2024",
        "COSMOS-2576",
        "rpo_shadowing",
        "2024-05",
        "COSMOS-2576 became coplanar with USA 314 in May 2024 and raised its "
        "orbit in February 2025.",
        end_epoch="2025-02",
        related_name=f"{TARGET_PREFIX}usa-314",
        confidence="high",
    ),
    _segment(
        "cosmos2558-usa326-2022",
        "COSMOS-2558",
        "rpo_shadowing",
        "2022-08",
        "COSMOS-2558 has been coplanar with USA 326 since August 2022.",
        related_name=f"{TARGET_PREFIX}usa-326",
        confidence="high",
        notes="No end recorded: the source describes it as ongoing.",
    ),
    # --- the 2025 formation ------------------------------------------------
    _segment(
        "cosmos2581-formation-2025",
        "COSMOS-2581",
        "rpo_inspection",
        "2025",
        "COSMOS-2581 and COSMOS-2582 flew in formation to within 100 m of "
        "each other, in a cluster acknowledged by the Russian MoD.",
        related_name="COSMOS-2582",
    ),
    _segment(
        "cosmos2582-formation-2025",
        "COSMOS-2582",
        "rpo_inspection",
        "2025",
        "COSMOS-2582 was the counterpart of COSMOS-2581 in a 100 m formation "
        "within the MoD-acknowledged 2025 cluster.",
        related_name="COSMOS-2581",
    ),
    _segment(
        "cosmos2583-pass-2025",
        "COSMOS-2583",
        "rpo_inspection",
        "2025",
        "COSMOS-2583 passed within 0.5 km within the 2025 cluster.",
        related_name="COSMOS-2581",
    ),
    # --- the GEO belt walkers ----------------------------------------------
    _segment(
        "sy12-01-drift",
        "SY-12 01",
        "longitudinal_drift",
        "2021",
        "SY-12-01 and SY-12-02 drift in opposite directions across the whole "
        "GEO belt, with turnaround points at 178.9°E over the Pacific and "
        "17.3°E over central Europe.",
        notes="Paired GEO inspectors. The turnaround points are the signature.",
    ),
    _segment(
        "sy12-02-drift",
        "SY-12 02",
        "longitudinal_drift",
        "2021",
        "SY-12-02 drifts opposite SY-12-01 across the GEO belt, between the "
        "same 178.9°E and 17.3°E turnaround points.",
    ),
    _segment(
        "olymp1-park",
        "Luch / Olymp-1",
        "station_keeping",
        "2024",
        "Olymp-1 parked near Intelsat 37e at 342°E before beginning its 2025 drift.",
        end_epoch="2025-03",
        related_name=None,
        observability="sparse",
        marker="INFERENCE",
        notes="Start epoch inferred from the drift beginning in March 2025.",
    ),
    _segment(
        "olymp1-drift-2025",
        "Luch / Olymp-1",
        "longitudinal_drift",
        "2025-03",
        "Olymp-1 began an eastward drift of 0.5°/day in March 2025.",
        confidence="high",
    ),
    _segment(
        "olymp2-visits",
        "Luch / Olymp-2",
        "rpo_inspection",
        "2024",
        "Olymp-2 visited Eutelsat Konnect, RASCOM-QAF-1, Astra 4A, Thor 7 and "
        "6, SES-5 and Intelsat 3-F7 and 10-02, closing to about 5 km from "
        "Thor 7 and under 1 km from Intelsat 10-02.",
        related_name=f"{TARGET_PREFIX}intelsat-10-02",
        marker="INFERENCE",
        notes="Start epoch is the earliest the source supports, not an observed date.",
    ),
    # --- the instants ------------------------------------------------------
    _segment(
        "tjs2-high-dv",
        "TJS-2",
        "anomalous_high_dv",
        "2024",
        "TJS-2 was tracked manoeuvring at 44 m/s, roughly 44 times the 0.5 to "
        "1 m/s GEO station-keeping baseline.",
        marker="INFERENCE",
        notes="Drawn as a node. The source gives no date beyond the reporting year.",
    ),
    _segment(
        "tjs4-solar-cone",
        "TJS-4",
        "rpo_shadowing",
        "2024",
        "TJS-4 manoeuvred to place itself between a US space surveillance "
        "satellite and the Sun, creating a disadvantageous imaging geometry.",
        related_name=f"{TARGET_PREFIX}us-space-surveillance-satellite",
        marker="INFERENCE",
        notes="The counterpart is not named by the source, only its role.",
    ),
    _segment(
        "shenlong3-release-2023",
        "PRC Test Spacecraft 3",
        "separation_event",
        "2023-12",
        "The third Shenlong flight released six objects after its December "
        "2023 launch.",
        confidence="high",
    ),
    _segment(
        "cosmos2553-tumbling",
        "COSMOS-2553",
        "quiescent",
        "2024-11",
        "COSMOS-2553 has been tumbling since about November 2024 on LeoLabs "
        "radar, and is assessed likely non-operational.",
        observability="moderate",
        marker="INFERENCE",
        notes="Tumbling, so no longer manoeuvring. Not a chosen quiescence.",
    ),
    _segment(
        "tjs10-tjs3-approach",
        "TJS-10",
        "rpo_inspection",
        "2024",
        "TJS-10 closed to 25 km of TJS-3.",
        related_name="TJS-3",
    ),
]
