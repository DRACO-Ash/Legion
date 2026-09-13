"""Seeded family assessments: the capability, context and intent synthesis.

This is the layer the whole application exists for. The same manoeuvre
signature serves inspection, servicing and attack, and what resolves the
ambiguity is capability plus context plus pattern of life. The catalogue
holds attributes and the timeline holds behaviour; this holds what a class
is, what it typically does, what its manoeuvre baseline is, and what should
raise concern.

Four rules govern every record here, taken from the content seed's own
provenance self-check and enforced by `tests/test_assessments.py`:

● **Nothing loads as a bare fact.** Every statement is a `Claim`.
● **A single-source claim loads at `moderate`, never `high`.** The one
  exception the source itself calls well-corroborated is SJ-21's capture,
  which CSIS describes as the only confirmed instance in GEO.
● **An unknown is a TBC claim with a named owner, never a guess.** Five of
  the fifteen families have no sourced assessment, and they say so and name
  who writes one, rather than being absent or quietly filled in.
● **Nothing is validated.** Every record loads with `validated_by` unset, so
  the interface shows "awaiting validation". An assessment reconstructed from
  open sources is not authoritative because it is written down, and who is
  entitled to sign one off is still Ash's decision.

The catalogue splits some of the research's lines across several families.
Nivelir is four, and SY is two. Each assessment is written against the
family id it actually attaches to, because one keyed to a line that is not a
catalogue family would never reach an analyst.
"""

from typing import Any

CSIS = "CSIS Space Threat Assessment 2025 (Swope, Bingen, Young, LaFave, April 2025)"
CSIS_USSF = f"{CSIS}; senior US Space Force characterisation, March 2025"
CSIS_CIS = f"{CSIS}; china-in-space.com SJ-25/SJ-21 reporting, January 2026"
ASSERTED_BY = "seed-loader, from deliverable/04-CONTENT-SEED.md"
TBC_OWNER = "Ash or a JCO subject-matter expert"

GEO_BASELINE = "GEO station-keeping, 0.5 to 1 m/s"
INSPECTION_RPO = "Inspection RPO"
THINK_TANK = "think_tank"
TBC = "tbc"


def _claim(
    statement: str,
    marker: str = "FACT",
    confidence: str = "moderate",
    citation: str = CSIS,
) -> dict[str, Any]:
    return {
        "statement": statement,
        "marker": marker,
        "confidence": confidence,
        "source_class": THINK_TANK,
        "source_citation": citation,
        "asserted_by": ASSERTED_BY,
    }


def _tbc(subject: str) -> dict[str, Any]:
    """An honest gap. Named owner, never a guess, never silently absent."""
    return {
        "statement": (
            f"No sourced assessment has been written for {subject}. This is a "
            "gap in the compendium, not an assessment that there is nothing to "
            "say."
        ),
        "marker": "INFERENCE",
        "confidence": "low",
        "source_class": TBC,
        "owner": TBC_OWNER,
        "asserted_by": ASSERTED_BY,
    }


def _capability(kind: str, label: str, claim: dict[str, Any]) -> dict[str, Any]:
    return {"kind": kind, "label": label, "claim": claim}


def _assessment(
    family_id: str,
    one_line: dict[str, Any],
    role_summary: dict[str, Any],
    *,
    manoeuvre_baseline: str | None = None,
    baseline_claim: dict[str, Any] | None = None,
    what_raises_concern: list[dict[str, Any]] | None = None,
    capabilities: list[dict[str, Any]] | None = None,
    open_questions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "family_id": family_id,
        "one_line": one_line,
        "role_summary": role_summary,
        "manoeuvre_baseline": manoeuvre_baseline,
        "baseline_claim": baseline_claim,
        "what_raises_concern": what_raises_concern or [],
        "capabilities": capabilities or [],
        "open_questions": open_questions or [],
        # Never set by a seed. Ash owns the validation route.
        "validated_by": None,
    }


def _thin(family_id: str, subject: str) -> dict[str, Any]:
    return _assessment(
        family_id,
        _tbc(subject),
        _tbc(f"the role of {subject}"),
        open_questions=[f"Write the sourced assessment for {subject}."],
    )


SEED_ASSESSMENTS: list[dict[str, Any]] = [
    _assessment(
        "chn-sj",
        _claim(
            "China's GEO on-orbit servicing and RPO line, dual-use: the same "
            "capabilities that service a satellite can harm one."
        ),
        _claim(
            "Experimental on-orbit servicing, inspection, refuelling and "
            "capture demonstrations in GEO."
        ),
        manoeuvre_baseline=GEO_BASELINE,
        baseline_claim=_claim(
            "Standard GEO station-keeping and repositioning runs at 0.5 to "
            "1 m/s, which is the figure a deviation should be read against."
        ),
        what_raises_concern=[
            _claim(
                "SJ-21 conducted the only confirmed noncooperative capture in "
                "GEO, towing a defunct Beidou satellite to a graveyard orbit "
                "in 2022.",
                confidence="high",
            ),
            _claim(
                "SJ-25 entered a coplanar orbit with SJ-21 in January 2025 and "
                "refuelled it in late 2025; the pair separated in mid-January "
                "2026 at about 50 km per day.",
                citation=CSIS_CIS,
            ),
            _claim(
                "TJS-3 moved within 1 degree of latitude of SJ-21 in January "
                "2025, which would be a supporting role.",
                marker="INFERENCE",
            ),
        ],
        capabilities=[
            _capability(
                "robotic_arm",
                "Robotic arm",
                _claim(
                    "SJ-17 and SJ-21 are assessed to carry a robotic arm.",
                    marker="INFERENCE",
                ),
            ),
            _capability(
                "noncooperative_capture",
                "Noncooperative capture",
                _claim(
                    "SJ-21 demonstrated capture and tow of an uncooperative object.",
                    confidence="high",
                ),
            ),
            _capability(
                "refuelling",
                "Refuelling",
                _claim(
                    "SJ-25 is assessed to have refuelled SJ-21 in late 2025.",
                    marker="INFERENCE",
                    citation=CSIS_CIS,
                ),
            ),
            _capability(
                "inspection_rpo",
                INSPECTION_RPO,
                _claim(
                    "The line conducts routine inspection proximity operations in GEO."
                ),
            ),
        ],
        open_questions=[
            "The exact payload of each SJ variant.",
            "Whether SJ-23 and SJ-28 are inspectors or servicers.",
            "The next SJ-25 target.",
        ],
    ),
    _assessment(
        "chn-sy12",
        _claim(
            "A paired GEO inspection capability that walks the entire "
            "geostationary belt, the Chinese analogue of GSSAP."
        ),
        _claim(
            "Two objects drifting in opposite directions across the belt, "
            "giving persistent coverage of GEO from both sides."
        ),
        manoeuvre_baseline=GEO_BASELINE,
        baseline_claim=_claim(
            "A belt-walking drift is a sustained regime, not a manoeuvre. The "
            "deviation to watch for is a stop or a reversal off the known "
            "turnaround points."
        ),
        what_raises_concern=[
            _claim(
                "SY-12-01 and SY-12-02 drift the whole GEO belt in opposite "
                "directions, with turnaround points at 178.9 degrees east over "
                "the Pacific and 17.3 degrees east over central Europe."
            ),
        ],
        capabilities=[
            _capability(
                "inspection_rpo",
                INSPECTION_RPO,
                _claim("Paired GEO inspectors with belt-wide reach."),
            ),
            _capability(
                "coplanar_shadowing",
                "Coplanar shadowing",
                _claim(
                    "Assessed capable of holding station alongside a GEO asset.",
                    marker="INFERENCE",
                ),
            ),
        ],
        open_questions=["Which assets the turnaround points were chosen for."],
    ),
    _assessment(
        "chn-dogfight",
        _claim(
            "China's LEO close-proximity demonstrators: the triads a senior US "
            "Space Force official publicly characterised as dogfighting in "
            "March 2025.",
            citation=CSIS_USSF,
        ),
        _claim(
            "Highly manoeuvrable LEO triads conducting corkscrew and sub-"
            "kilometre proximity operations against other Chinese objects, "
            "with short operational lives and subsatellite release."
        ),
        manoeuvre_baseline=(
            "No published LEO baseline. Judge against the class's own history "
            "rather than an absolute figure."
        ),
        baseline_claim=_tbc("the LEO manoeuvre baseline for this class"),
        what_raises_concern=[
            _claim(
                "The SY-24C triad conducted corkscrew RPO around SJ-6-05B and "
                "closed to under 1 km of SJ-6-05A, described as essentially "
                "face to face at about 17,000 mph.",
                citation=CSIS_USSF,
            ),
            _claim(
                "The specific sub-kilometre figure rests on a US Space Force "
                "fact sheet cited at second hand, so it is carried as an "
                "inference until the primary is obtained.",
                marker="INFERENCE",
                confidence="low",
                citation=CSIS_USSF,
            ),
        ],
        capabilities=[
            _capability(
                "inspection_rpo",
                "Close-proximity RPO",
                _claim(
                    "Demonstrated repeated sub-kilometre proximity operations.",
                    citation=CSIS_USSF,
                ),
            ),
            _capability(
                "high_delta_v_manoeuvre",
                "High delta-v manoeuvre",
                _claim(
                    "Corkscrew profiles imply a manoeuvre budget well beyond "
                    "station-keeping.",
                    marker="INFERENCE",
                ),
            ),
            _capability(
                "sub_object_release",
                "Sub-object release",
                _claim("Subsatellite release is recorded for the class."),
            ),
        ],
        open_questions=[
            "Whether the counterparts were cooperative participants or targets.",
            "Obtain the primary US Space Force fact sheet for the sub-km figure.",
        ],
    ),
    _assessment(
        "chn-tjs",
        _claim(
            "A suspected military early-warning and signals-intelligence GEO "
            "line, several members of which have demonstrated inspection and "
            "evasive geometry."
        ),
        _claim(
            "Signals collection from GEO, with RPO and subsatellite release "
            "demonstrated across the series."
        ),
        manoeuvre_baseline=GEO_BASELINE,
        baseline_claim=_claim(
            "Against the 0.5 to 1 m/s GEO baseline, TJS-2's 44 m/s manoeuvre "
            "is roughly 44 times normal. The anomaly is the ratio, not the "
            "absolute figure."
        ),
        what_raises_concern=[
            _claim(
                "TJS-4 manoeuvred to place itself between a US space "
                "surveillance satellite and the Sun, creating a "
                "disadvantageous imaging geometry."
            ),
            _claim("TJS-2 manoeuvred at 44 m/s, about 44 times the GEO baseline."),
            _claim("TJS-10 closed to 25 km of TJS-3 in May 2024."),
        ],
        capabilities=[
            _capability(
                "sigint_payload",
                "SIGINT payload",
                _claim(
                    "The line is assessed to carry signals-collection payloads.",
                    marker="INFERENCE",
                ),
            ),
            _capability(
                "inspection_rpo",
                INSPECTION_RPO,
                _claim("TJS-10 demonstrated a 25 km closing approach on TJS-3."),
            ),
            _capability(
                "high_delta_v_manoeuvre",
                "High delta-v manoeuvre",
                _claim(
                    "TJS-2 demonstrated a manoeuvre far outside the class baseline."
                ),
            ),
        ],
        open_questions=["Which US asset TJS-4 positioned against."],
    ),
    _assessment(
        "rus-luch",
        _claim(
            "Russia's GEO signals-intelligence loiter line, parking near "
            "commercial and allied communications satellites over regions of "
            "interest."
        ),
        _claim(
            "The pattern of life is the signature: a loiterer takes up station "
            "beside a comms satellite and stays, rather than manoeuvring "
            "conspicuously."
        ),
        manoeuvre_baseline=GEO_BASELINE,
        baseline_claim=_claim(
            "A loiter is station-keeping by another name, so the departure "
            "from baseline is the drift between targets, not the loiter."
        ),
        what_raises_concern=[
            _claim(
                "Olymp-2 visited Eutelsat Konnect, RASCOM-QAF-1, Astra 4A, "
                "Thor 7 and 6, SES-5 and Intelsat 3-F7 and 10-02, closing to "
                "about 5 km from Thor 7 and under 1 km from Intelsat 10-02."
            ),
            _claim(
                "Olymp-2's arrival near Astra 4A coincided with ground jamming "
                "of Ukrainian broadcasts. The co-occurrence is reported; the "
                "causal link is not established and CSIS says so explicitly.",
                marker="SPECULATION",
                confidence="low",
            ),
        ],
        capabilities=[
            _capability(
                "sigint_payload",
                "SIGINT payload",
                _claim(
                    "The line's purpose is assessed as signals collection.",
                    marker="INFERENCE",
                ),
            ),
            _capability(
                "coplanar_shadowing",
                "Loiter alongside a target",
                _claim(
                    "Demonstrated sustained station beside commercial comms satellites."
                ),
            ),
        ],
        open_questions=["Which collection the target set implies."],
    ),
]

# The Nivelir line's assessment, written once and attached to each of the four
# catalogue families it covers, with the concern specific to that cluster.
_NIVELIR_ONE_LINE = (
    "Russia's co-orbital inspector line, following a nesting-doll release "
    "pattern, with several members coplanar with US assets and assessed by "
    "the US Space Force as counterspace weapons."
)
_NIVELIR_ROLE = (
    "Co-orbital inspection in LEO, with sub-payload release, conducted "
    "against both Russian and US objects."
)
_NIVELIR_CONCERNS: dict[str, list[dict[str, Any]]] = {
    "rus-nivelir1": [],
    "rus-nivelir2": [
        _claim(
            "The 2019 payloads had characteristics resembling previously "
            "deployed counterspace payloads, on a US assessment."
        )
    ],
    "rus-nivelir3": [
        _claim("COSMOS-2558 has been coplanar with USA 326 since August 2022.")
    ],
    "rus-nivelir45": [
        _claim(
            "COSMOS-2576 entered a coplanar orbit with USA 314 in May 2024 and "
            "raised its orbit in February 2025."
        )
    ],
}

SEED_ASSESSMENTS += [
    _assessment(
        family_id,
        _claim(_NIVELIR_ONE_LINE),
        _claim(_NIVELIR_ROLE),
        manoeuvre_baseline=(
            "No published LEO baseline for the line. A plane match with a "
            "foreign asset is the signal, not the delta-v."
        ),
        baseline_claim=_tbc("the LEO manoeuvre baseline for the Nivelir line"),
        what_raises_concern=concerns,
        capabilities=[
            _capability(
                "coplanar_shadowing",
                "Coplanar shadowing",
                _claim("The line has repeatedly matched planes with US assets."),
            ),
            _capability(
                "sub_object_release",
                "Sub-object release",
                _claim("The nesting-doll pattern is the line's signature."),
            ),
            _capability(
                "kinetic_kill_vehicle",
                "Kinetic kill vehicle",
                _claim(
                    "Assessed for some members of the line, not confirmed per "
                    "object. Carried as an inference for that reason.",
                    marker="INFERENCE",
                    confidence="low",
                ),
            ),
        ],
        open_questions=["Which specific members carry a kinetic payload."],
    )
    for family_id, concerns in _NIVELIR_CONCERNS.items()
]

# Families with no sourced assessment yet. Present and honest rather than
# absent: a missing family reads as nothing to say, which is a different claim.
SEED_ASSESSMENTS += [
    _thin("chn-shenlong", "the Shenlong reusable spaceplane line"),
    _thin("chn-sj6", "the SJ-6 objects carried as dogfighting counterparts"),
    _thin("rus-2026", "the 2026 Russian manoeuvrable cluster"),
    _thin("rus-egeo", "the eGEO Nivelir extension"),
    _thin("rus-numizmat", "the Numizmat and Naveska cluster"),
    _thin("rus-testbed", "the Russian technology testbeds"),
]
