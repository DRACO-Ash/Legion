"""Side-by-side comparison of two to four objects or families.

The cross-system comparison use case: an analyst holding one manoeuvre
signature wants to know how this class differs from that one, and the answer
is spread across the catalogue, the assessment and the timeline.

Two rules shape the assembly.

● **A cell says why it is empty.** A comparison is mostly a search for
  differences, and a blank cell reads as "no capability" when it often means
  "nobody has written this down". Every absent value carries a reason.
● **Provenance travels with the value.** A capability sourced to a think tank
  and one sourced to an analyst's own reasoning are different objects, and a
  comparison that flattens them into two ticks is worse than no comparison.

Between two and four. One is not a comparison, and past four the columns are
too narrow to read on the panel the specification asks for.
"""

from __future__ import annotations

from typing import Any

from src.graph import FAMILY_PREFIX
from src.pol import MODE_LABELS

MIN_SUBJECTS = 2
MAX_SUBJECTS = 4

NOT_RECORDED = "not recorded"
NO_ASSESSMENT = "no assessment written"
NOT_CATALOGUED = "not in the catalogue"

OBJECT_FIELDS: tuple[tuple[str, str], ...] = (
    ("nation", "Nation"),
    ("regime", "Regime"),
    ("norad_id", "NORAD id"),
    ("launch_year", "Launch year"),
    ("launch_site", "Launch site"),
    ("status", "Status"),
    ("delta_v", "Observed manoeuvres"),
    ("coplanar", "Coplanar with"),
)


def _cell(value: Any, absent: str = NOT_RECORDED) -> dict[str, Any]:
    """One value, or the reason there is none.

    Never a bare empty string: in a comparison an empty cell is read as a
    finding, and "no robotic arm" is a different claim from "nobody has
    written down whether it has one".
    """
    if value in (None, "", []):
        return {"value": None, "absent": absent}
    return {"value": value, "absent": None}


def _capability_rows(capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "kind": capability.get("kind"),
            "label": capability.get("label"),
            "marker": (capability.get("claim") or {}).get("marker"),
            "confidence": (capability.get("claim") or {}).get("confidence"),
            "citation": (capability.get("claim") or {}).get("source_citation"),
        }
        for capability in capabilities
    ]


def _behaviour_summary(segments: list[dict[str, Any]]) -> list[str]:
    """The modes this object has been assessed in, most recent first."""
    live = [s for s in segments if not s.get("archived")]
    live.sort(key=lambda s: str(s.get("start_epoch") or ""), reverse=True)
    return [
        f"{MODE_LABELS.get(str(s.get('mode')), str(s.get('mode')))}, "
        f"{s.get('start_epoch')}"
        for s in live
    ]


def _object_subject(
    record: dict[str, Any],
    layer: dict[str, Any],
    assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    """One catalogued object, with the class baseline it is judged against.

    The baseline comes from the family assessment rather than the record,
    because a delta-v figure is only legible as a deviation against the
    class it belongs to.
    """
    return {
        "id": record["id"],
        "kind": "object",
        "label": record.get("catalogue_name"),
        "family_id": record.get("family_id"),
        "family_title": record.get("family_title"),
        "attributes": {
            label: _cell(record.get(field)) for field, label in OBJECT_FIELDS
        },
        "baseline": _cell((assessment or {}).get("manoeuvre_baseline"), NO_ASSESSMENT),
        "capabilities": _capability_rows((assessment or {}).get("capabilities", [])),
        "behaviour": _behaviour_summary(layer.get("pol_segments", [])),
        "claims": len([c for c in layer.get("claims", []) if not c.get("archived")]),
        # An object's baseline and capabilities are its family's, so the
        # family's validation state is the object's too. Without this an
        # object briefing carried capabilities from an unvalidated assessment
        # and said nothing about it, which is how an assessment becomes a
        # fact on its way to somebody else's desk.
        "awaiting_validation": _awaiting(assessment),
    }


def _awaiting(assessment: dict[str, Any] | None) -> bool:
    return assessment is None or not str(assessment.get("validated_by") or "").strip()


def _family_subject(
    family_id: str,
    members: list[dict[str, Any]],
    assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    first = members[0]
    regimes = sorted({str(m.get("regime")) for m in members if m.get("regime")})
    return {
        "id": FAMILY_PREFIX + family_id,
        "kind": "family",
        "label": first.get("family_title") or family_id,
        "family_id": family_id,
        "family_title": first.get("family_title"),
        "attributes": {
            "Nation": _cell(first.get("nation")),
            "Regime": _cell(", ".join(regimes)),
            "Members": _cell(len(members)),
            "One line": _cell(
                ((assessment or {}).get("one_line") or {}).get("statement"),
                NO_ASSESSMENT,
            ),
        },
        "baseline": _cell((assessment or {}).get("manoeuvre_baseline"), NO_ASSESSMENT),
        "capabilities": _capability_rows((assessment or {}).get("capabilities", [])),
        "behaviour": [],
        "awaiting_validation": _awaiting(assessment),
    }


def _rows(subjects: list[dict[str, Any]]) -> list[str]:
    """Every attribute row any subject carries, in a stable order.

    Objects and families do not share an attribute set, so comparing one of
    each would otherwise silently drop whichever rows the first subject
    happened not to have.
    """
    seen: list[str] = []
    for subject in subjects:
        for label in subject["attributes"]:
            if label not in seen:
                seen.append(label)
    return seen


def build_comparison(subjects: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(subjects),
        "rows": _rows(subjects),
        "subjects": subjects,
    }
