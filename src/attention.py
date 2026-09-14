"""The attention queue: an indicative order over what the store already holds.

Ash's decision, 14 September 2026: **the application may rank what needs
attention as an indicative element only, and that ranking goes nowhere else.**
`src/ranking_policy.py` carries the rule and its four boundaries; this module
is the part that obeys them.

How it obeys the fourth boundary, which is the hard one. "The ordering inputs
must themselves be sourced" means this module may arrange facts the store
already records, and may not invent a judgement of its own. Every reason a
subject appears here is a **stored field**, named in the entry:

● a family assessment with `validated_by` unset is unsigned
● an assessment field whose `source_class` is `tbc` is unverified and names
  who must verify it
● a catalogue record with no `norad_id` cannot be plotted or charted
● a `pol_segment` with no `end_epoch` has no recorded end

No severity, no weight, no threat score, because none of those is a thing the
sources say. The order is the order of those categories, and the category is
printed beside every entry, so a reader can disagree with the ordering without
having to guess what produced it.

**Every shape in here was read off a real seeded store rather than assumed**,
and three of the first guesses were wrong: object `claims` are empty because
claims are analyst-created, the segment collection is `pol_segments` and not
`segments`, and TBC is a `source_class` and not a marker. An entry keyed off
any of those would have produced a queue that was silently always empty.

Nothing here is ever written back. It is rebuilt per request from the store,
which is what makes "computed for display and never stored" true rather than
merely intended.
"""

from __future__ import annotations

from typing import Any

from src.ranking_policy import INDICATIVE_LABEL
from src.ranking_policy import policy as ranking_policy

# The categories, in the order they are shown. Each is a fact the store holds,
# and the wording is what the interface prints, so an analyst reads the reason
# rather than a rank number.
UNVERIFIED = "Unverified, needs re-checking"
UNSIGNED = "Assessment written but unsigned"
OPEN_BEHAVIOUR = "Behaviour with no recorded end"
OFF_PLOT = "No catalogue number, so it cannot be plotted"

CATEGORY_ORDER = (UNVERIFIED, UNSIGNED, OPEN_BEHAVIOUR, OFF_PLOT)

# Assessment fields that carry a Claim and can therefore be marked TBC.
CLAIM_FIELDS = ("one_line", "role_summary", "baseline_claim")

TBC_SOURCE_CLASS = "tbc"


def _entry(
    *,
    subject: str,
    subject_id: str | None,
    category: str,
    detail: str,
    marker: str | None = None,
    citation: str | None = None,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "subject_id": subject_id,
        "category": category,
        "detail": detail,
        "marker": marker,
        "citation": citation,
    }


def _family_titles(records: list[dict[str, Any]]) -> dict[str, str]:
    """family_id to the title an analyst would recognise.

    Assessment records carry `family_id` and no title, so without this the
    queue prints a slug like `chn-dogfight`. Showing a reader an internal key
    is the same defect as rendering a raw uuid, which this interface has been
    caught doing twice before.
    """
    titles: dict[str, str] = {}
    for record in records:
        family_id = str(record.get("family_id") or "")
        title = str(record.get("family_title") or "").strip()
        if family_id and title:
            titles.setdefault(family_id, title)
    return titles


def _tbc_fields(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """The assessment claims still carrying the TBC source class."""
    claims = []
    for field in CLAIM_FIELDS:
        claim = entry.get(field)
        if not isinstance(claim, dict):
            continue
        if str(claim.get("source_class", "")).lower() == TBC_SOURCE_CLASS:
            claims.append(claim)
    return claims


def _one_assessment(
    family_id: str, entry: dict[str, Any], subject: str
) -> list[dict[str, Any]]:
    """Everything one family assessment puts on the queue."""
    found = [
        _entry(
            subject=subject,
            subject_id=f"family:{family_id}",
            category=UNVERIFIED,
            detail=str(claim.get("statement") or "").strip(),
            marker=str(claim.get("marker") or "").strip() or None,
            citation=str(claim.get("asserted_by") or "").strip() or None,
        )
        for claim in _tbc_fields(entry)
    ]
    if not str(entry.get("validated_by") or "").strip():
        found.append(
            _entry(
                subject=subject,
                subject_id=f"family:{family_id}",
                category=UNSIGNED,
                detail=(
                    "Written but not signed off. Any member of the DOK team "
                    "may sign it."
                ),
            )
        )
    return found


def _assessment_entries(
    assessments: dict[str, Any], titles: dict[str, str]
) -> list[dict[str, Any]]:
    """Unsigned assessments, and assessment claims still marked TBC."""
    found: list[dict[str, Any]] = []
    for family_id, entry in sorted(assessments.items()):
        if isinstance(entry, dict) and not entry.get("archived"):
            found.extend(
                _one_assessment(family_id, entry, titles.get(family_id, family_id))
            )
    return found


def _open_behaviour_entries(
    name: str, record_id: str, layer: dict[str, Any]
) -> list[dict[str, Any]]:
    """Segments with no recorded end.

    "No end recorded" is the fact and this module does not upgrade it to
    "ongoing". Where a source does say a behaviour continues, as for
    COSMOS-2558, the claim says so and the claim is what is shown.
    """
    return [
        _entry(
            subject=name,
            subject_id=record_id,
            category=OPEN_BEHAVIOUR,
            detail=str(
                (segment.get("claim") or {}).get("statement")
                or segment.get("notes")
                or ""
            ).strip(),
            marker=str((segment.get("claim") or {}).get("marker") or "").strip()
            or None,
            citation=str(
                (segment.get("claim") or {}).get("source_citation") or ""
            ).strip()
            or None,
        )
        for segment in layer.get("pol_segments", [])
        if not segment.get("archived") and not segment.get("end_epoch")
    ]


def _one_record(record: dict[str, Any], layer: dict[str, Any]) -> list[dict[str, Any]]:
    """Everything one catalogue record puts on the queue."""
    name = str(record.get("catalogue_name") or "unnamed")
    record_id = str(record.get("id"))
    found = _open_behaviour_entries(name, record_id, layer)
    if not record.get("norad_id"):
        found.append(
            _entry(
                subject=name,
                subject_id=record_id,
                category=OFF_PLOT,
                detail=(
                    "The source names a behaviour, not a catalogue entry, so "
                    "this is excluded from the belt and the charts."
                ),
                citation=str(record.get("verify_owner") or "").strip() or None,
            )
        )
    return found


def _object_entries(
    records: list[dict[str, Any]], objects: dict[str, Any]
) -> list[dict[str, Any]]:
    """What the catalogue and the behavioural history say about each object."""
    found: list[dict[str, Any]] = []
    for record in records:
        if not record.get("archived"):
            found.extend(_one_record(record, objects.get(str(record.get("id"))) or {}))
    return found


def build_attention(
    *,
    records: list[dict[str, Any]],
    objects: dict[str, Any],
    assessments: dict[str, Any],
    limit: int = 14,
) -> dict[str, Any]:
    """The queue, rebuilt from the store on every request.

    The response carries the policy with it, so a caller cannot show the order
    without also being handed the words that say what the order is worth.
    """
    titles = _family_titles(records)
    entries = _assessment_entries(assessments, titles) + _object_entries(
        records, objects
    )
    entries.sort(key=lambda entry: CATEGORY_ORDER.index(entry["category"]))

    counts = {category: 0 for category in CATEGORY_ORDER}
    for entry in entries:
        counts[entry["category"]] += 1

    # Take the head of each category rather than the head of the whole list.
    # A strict prefix was worse than it looked: with seventeen unverified and
    # fifteen unsigned, the first fourteen were all assessments and the twenty
    # open behaviours were unreachable, while the category counts told the
    # analyst they existed. Every populated category is now represented.
    shown: list[dict[str, Any]] = []
    per_category = max(1, limit // len(CATEGORY_ORDER))
    for category in CATEGORY_ORDER:
        shown.extend(
            [entry for entry in entries if entry["category"] == category][:per_category]
        )

    return {
        "label": INDICATIVE_LABEL,
        "policy": ranking_policy(),
        "count": len(entries),
        "shown": len(shown),
        "entries": shown,
        "categories": [
            {"name": category, "count": counts[category]} for category in CATEGORY_ORDER
        ],
    }
