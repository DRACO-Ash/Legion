"""The dossier: one object, everything held about it, in one place.

Selecting an object used to fill six panels spread down the page, and the
analyst had to scroll to each to find out whether it held anything. This
module answers that question first: for one object, how much is in each
section, what is still open on it, and whether it can be charted at all, so
the interface can label every section with what is behind it before the
analyst opens it.

Everything here is a count of what the store already holds or a stored field
read back, in the same spirit as the attention queue. Nothing is weighted,
nothing is scored and nothing is written. A section with nothing in it says
so, because an empty tab that looks like an unloaded tab is a defect this
interface has shipped before.
"""

from __future__ import annotations

from typing import Any

from src.compendium_models import INSTANTANEOUS_MODES

RECORD = "record"
PROVENANCE = "provenance"
BEHAVIOUR = "behaviour"
ASSESSMENT = "assessment"
CONNECTIONS = "connections"

SECTION_ORDER = (RECORD, PROVENANCE, BEHAVIOUR, ASSESSMENT, CONNECTIONS)

SIGNED = "signed"
UNSIGNED = "unsigned"
NO_ASSESSMENT = "none"


def _live(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if not item.get("archived")]


def _is_open(segment: dict[str, Any]) -> bool:
    """No recorded end, and a mode that can have one. Mirrors the queue."""
    return not segment.get("end_epoch") and segment.get("mode") not in (
        INSTANTANEOUS_MODES
    )


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _assessment_state(assessment: dict[str, Any] | None) -> str:
    if not assessment or assessment.get("archived"):
        return NO_ASSESSMENT
    if str(assessment.get("validated_by") or "").strip():
        return SIGNED
    return UNSIGNED


def _tbc_count(assessment: dict[str, Any] | None) -> int:
    if not assessment:
        return 0
    return sum(
        1
        for value in assessment.values()
        if isinstance(value, dict)
        and str(value.get("source_class", "")).lower() == "tbc"
    )


def _assessment_summary(assessment: dict[str, Any] | None) -> str:
    state = _assessment_state(assessment)
    if state == NO_ASSESSMENT:
        return "No family assessment held"
    tbc = _tbc_count(assessment)
    signed = "Signed off" if state == SIGNED else "Not signed off"
    if tbc:
        return f"{signed}, {_plural(tbc, 'statement')} to verify"
    return signed


def _behaviour_summary(segments: list[dict[str, Any]]) -> str:
    if not segments:
        return "No assessed behaviour recorded"
    open_count = sum(1 for segment in segments if _is_open(segment))
    summary = _plural(len(segments), "segment")
    if open_count:
        summary += f", {open_count} with no recorded end"
    return summary


def _section(
    key: str, label: str, count: int | None, summary: str, *, empty: bool
) -> dict[str, Any]:
    """`empty` is stated, not left to be inferred from `count`.

    The two differ for the assessment, whose count is the statements still to
    verify: an assessment with none to verify is complete, not empty, and the
    interface dimmed it as empty until the server said which it was.
    """
    return {
        "key": key,
        "label": label,
        "count": count,
        "summary": summary,
        "empty": empty,
    }


def build_dossier(
    *,
    record: dict[str, Any],
    layer: dict[str, Any],
    assessment: dict[str, Any] | None,
    edge_count: int,
    outstanding: list[dict[str, Any]],
) -> dict[str, Any]:
    """What is held about one object, section by section.

    `outstanding` is the attention queue already narrowed to this object and
    its family, so the dossier and the queue cannot disagree about what is
    open: they are the same entries, read once.
    """
    claims = _live(layer.get("claims", []))
    segments = _live(layer.get("pol_segments", []))
    norad = record.get("norad_id")

    sections = [
        _section(
            RECORD, "Record", None, "Catalogue fields, editable here", empty=False
        ),
        _section(
            PROVENANCE,
            "Provenance",
            len(claims),
            _plural(len(claims), "claim") if claims else "No claims recorded yet",
            empty=not claims,
        ),
        _section(
            BEHAVIOUR,
            "Behaviour",
            len(segments),
            _behaviour_summary(segments),
            empty=not segments,
        ),
        _section(
            ASSESSMENT,
            "Assessment",
            _tbc_count(assessment),
            _assessment_summary(assessment),
            empty=_assessment_state(assessment) == NO_ASSESSMENT,
        ),
        _section(
            CONNECTIONS,
            "Connections",
            edge_count,
            _plural(edge_count, "sourced link") if edge_count else "Nothing linked",
            empty=edge_count == 0,
        ),
    ]

    return {
        "subject_id": record["id"],
        "name": record.get("catalogue_name"),
        "family_id": record.get("family_id"),
        "family_title": record.get("family_title"),
        "archived": bool(record.get("archived")),
        "assessment_state": _assessment_state(assessment),
        "chartable": bool(norad),
        "chart_note": (
            "Movement reads live UDL element sets for this catalogue number."
            if norad
            else "No catalogue number, so this object cannot be charted."
        ),
        "sections": sections,
        "outstanding": outstanding,
        "outstanding_count": len(outstanding),
    }
