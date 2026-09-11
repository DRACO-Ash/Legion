"""Systems named in the research but absent from the canonical 49.

Why this is a separate module from `seed_data.py`. That file is a verbatim
mirror of `Red_ASAT_Systems.xlsx` by way of `tactics_wiki.html`, and the
standing rule is that its values are not re-derived from anywhere else. These
records come from somewhere else: the research strands committed under
`deliverable/research/`, whose primary source is the CSIS Space Threat
Assessment 2025. Mixing the two in one file would make the canonical mirror
unverifiable, because nobody could tell by looking which rows came from the
spreadsheet.

So they live here, and they are marked. Three rules make the distinction
structural rather than a comment, and `tests/test_candidate_systems.py`
enforces each one:

● **No candidate carries a NORAD catalogue number.** The research names
  behaviours, not catalogue entries, and inventing a satellite number is the
  one error in this domain that looks exactly like data. Charts already
  exclude an object with no NORAD id and say why (`SKIP_NO_NORAD_ID`), so a
  candidate is visibly uncharted rather than silently wrong.
● **Every candidate cites the material it came from**, in the same way a
  `Claim` must. A record an analyst cannot trace is worse than an absent one.
● **Every candidate names who must verify it.** This is the TBC-with-an-owner
  rule from the compendium, applied to the catalogue: an unverified entry has
  to name the person who resolves it, or it sits there for ever.

Fields left `None` are fields the source does not state. Do not fill one in
from memory. The route to promoting a candidate into the catalogue proper is
a live UDL cross-check, which resolves the NORAD id, the launch year and the
status together.
"""

from typing import Any

CSIS_2025 = (
    "CSIS Space Threat Assessment 2025 (Swope, Bingen, Young, LaFave, "
    "April 2025), via deliverable/research/02_domain_counterspace.md"
)
VERIFY_OWNER = "Ash, cross-check against a live UDL session"
CANDIDATE_FLAG = "Candidate — not in the canonical 49, verify"

LUCH_OLYMP_TITLE = "Luch / Olymp — GEO SIGINT Loiterers"
LUCH_OLYMP_SUB = (
    "Parks alongside commercial comms satellites; the loiter is the signature"
)
TJS_TITLE = 'TJS "Four Heavenly Kings" — Signals Collection'
TJS_SUB = "GEO signals-collection cluster with RPO and subsatellite release"
SJ6_TITLE = "Shijian-6 (SJ-6) — Dogfighting Counterparts"
SJ6_SUB = "The objects the SY-24C triad manoeuvred around, LEO"
TESTBED_TITLE = "Russian Technology Testbeds"
TESTBED_SUB = "Single objects that do not belong to a named inspector line"

_UNKNOWN = "unknown"
_GEO = "GEO"
_LEO = "LEO"
_MEO = "MEO"
_NOT_STATED = " Launch year, site and NORAD id are not stated by the source."


def _candidate(**fields: Any) -> dict[str, Any]:
    """One candidate, with the fields the source does not state left empty.

    Defaults are set here rather than repeated on every record so that adding
    a record cannot accidentally assert a launch year or a catalogue number by
    forgetting to leave one out.
    """
    record: dict[str, Any] = {
        "designator": None,
        "launch_year": None,
        "launch_site": None,
        "norad_id": None,
        "delta_v": None,
        "status": _UNKNOWN,
        "life": None,
        "coplanar": None,
        "flag": CANDIDATE_FLAG,
        "source_citation": CSIS_2025,
        "verify_owner": VERIFY_OWNER,
    }
    record.update(fields)
    record["notes"] = record["notes"] + _NOT_STATED
    return record


CANDIDATE_RECORDS: list[dict[str, Any]] = [
    _candidate(
        candidate_key="rus-luch/olymp-1",
        family_id="rus-luch",
        family_title=LUCH_OLYMP_TITLE,
        family_sub=LUCH_OLYMP_SUB,
        nation="RU",
        catalogue_name="Luch / Olymp-1",
        regime=_GEO,
        delta_v="0.5°/day eastward drift from March 2025",
        notes=(
            "Parked near Intelsat 37e at 342°E, then began a 0.5°/day eastward "
            "drift in March 2025. A SIGINT loiterer parks near comms satellites "
            "over regions of interest, so the pattern of life is the signature."
        ),
    ),
    _candidate(
        candidate_key="rus-luch/olymp-2",
        family_id="rus-luch",
        family_title=LUCH_OLYMP_TITLE,
        family_sub=LUCH_OLYMP_SUB,
        nation="RU",
        catalogue_name="Luch / Olymp-2",
        regime=_GEO,
        coplanar="Thor 7, Intelsat 10-02",
        notes=(
            "Visited Eutelsat Konnect, RASCOM-QAF-1, Astra 4A, Thor 7 and 6, "
            "SES-5, Intelsat 3-F7 and 10-02. Closed to about 5 km from Thor 7 "
            "and under 1 km from Intelsat 10-02."
        ),
    ),
    _candidate(
        candidate_key="rus-testbed/cosmos-2553",
        family_id="rus-testbed",
        family_title=TESTBED_TITLE,
        family_sub=TESTBED_SUB,
        nation="RU",
        catalogue_name="COSMOS-2553",
        regime=_MEO,
        notes=(
            "Suspected nuclear-ASAT-related technology testbed in a 2,000 km, "
            "high-radiation orbit. Tumbling since about November 2024 on LeoLabs "
            "radar, so assessed likely non-operational. Regime recorded as MEO "
            "from the stated altitude."
        ),
    ),
    _candidate(
        candidate_key="chn-tjs/tjs-2",
        family_id="chn-tjs",
        family_title=TJS_TITLE,
        family_sub=TJS_SUB,
        nation="CN",
        designator="TJS-2",
        catalogue_name="TJS-2",
        regime=_GEO,
        delta_v="44 m/s manoeuvre, about 44x the 0.5-1 m/s GEO baseline",
        notes=(
            "Tracked manoeuvring at 44 m/s, called out as unusually high against "
            "a 0.5-1 m/s GEO station-keeping baseline. The anomaly is the "
            "deviation from the class baseline, not the absolute figure."
        ),
    ),
    _candidate(
        candidate_key="chn-tjs/tjs-4",
        family_id="chn-tjs",
        family_title=TJS_TITLE,
        family_sub=TJS_SUB,
        nation="CN",
        designator="TJS-4",
        catalogue_name="TJS-4",
        regime=_GEO,
        notes=(
            "Manoeuvred to put itself between a US space surveillance satellite "
            "and the Sun, creating a disadvantageous imaging geometry. A named, "
            "repeatable tactic rather than a one-off manoeuvre."
        ),
    ),
    _candidate(
        candidate_key="chn-sj6/sj-6-05a",
        family_id="chn-sj6",
        family_title=SJ6_TITLE,
        family_sub=SJ6_SUB,
        nation="CN",
        catalogue_name="SJ-6-05A",
        regime=_LEO,
        coplanar="SHIYAN 24C 01, SHIYAN 24C 02, SHIYAN 24C 03",
        notes=(
            "SY-24C closed to under 1 km, described as essentially face to face "
            "at about 17,000 mph. Carried because a proximity segment must name "
            "its counterpart. Note the source names 05A for the sub-kilometre "
            "pass and 05B for the corkscrews: both are recorded, and which "
            "object was which is part of what needs verifying."
        ),
    ),
    _candidate(
        candidate_key="chn-sj6/sj-6-05b",
        family_id="chn-sj6",
        family_title=SJ6_TITLE,
        family_sub=SJ6_SUB,
        nation="CN",
        catalogue_name="SJ-6-05B",
        regime=_LEO,
        coplanar="SHIYAN 24C 01, SHIYAN 24C 02, SHIYAN 24C 03",
        notes=(
            "Named as the object the SY-24C triad flew corkscrew manoeuvres "
            "around, the behaviour a senior US Space Force official publicly "
            "characterised as dogfighting in March 2025."
        ),
    ),
]
