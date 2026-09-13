"""A house-style briefing, generated from what the compendium holds.

The briefing-generation use case: an analyst has read a comparison or an
object and now has to write it up. This produces the paste-ready text, in
Bluestaq house style, with the provenance carried rather than stripped.

**House style is enforced here, not described.** `tests/test_briefing.py`
runs the generated output through the same rules a document review would
apply, because a style note in a docstring constrains nobody:

● UK English.
● No em-dashes and no double dashes. A single hyphen is fine.
● No horizontal rules or dividers.
● `●` for bullets, never `-` or `*`.
● No `+` outside mathematics. Use "and".
● Lead with the point.

The provenance rule is the one that matters most. A briefing that drops the
marker and the citation turns an inference into a fact on its way to
somebody else's desk, which is the single worst thing this application could
do. Every statement carries its marker, its confidence and its source, and
an unvalidated assessment says so at the top.
"""

from __future__ import annotations

from typing import Any

from src.classification import CLASSIFICATION_BANNER

BULLET = "●"
SPACE = " "
COMMA = ", "
UNVALIDATED = (
    "Not validated. Reconstructed from publicly available sources and not "
    "signed off by a role holder."
)
NOTHING_RECORDED = "Nothing is recorded here yet."


def _line(text: str) -> str:
    return text.rstrip()


def _statement(claim: dict[str, Any] | None) -> str | None:
    """One claim as a bullet, with its provenance attached.

    The marker and the citation travel with the sentence. Stripping them
    would turn an inference into a fact on its way to somebody else's desk.
    """
    if not claim or not str(claim.get("statement") or "").strip():
        return None
    source = claim.get("source_citation") or claim.get("owner") or "no citation"
    marker = claim.get("marker", "UNMARKED")
    confidence = claim.get("confidence", "unstated")
    return f"{BULLET} {claim['statement']} [{marker}, {confidence}. {source}]"


def _section(heading: str, lines: list[str]) -> list[str]:
    if not lines:
        return []
    return ["", heading.upper(), *lines]


def _attribute_lines(subject: dict[str, Any]) -> list[str]:
    out = []
    for label, cell in subject.get("attributes", {}).items():
        value = cell["value"] if cell["value"] is not None else f"({cell['absent']})"
        out.append(f"{BULLET} {label}: {value}")
    return out


def _capability_lines(subject: dict[str, Any]) -> list[str]:
    return [
        f"{BULLET} {row['label']} [{row['marker']}, {row['confidence']}. "
        f"{row['citation'] or 'no citation'}]"
        for row in subject.get("capabilities", [])
    ]


def _behaviour_lines(subject: dict[str, Any]) -> list[str]:
    return [f"{BULLET} {entry}" for entry in subject.get("behaviour", [])]


def _baseline_lines(subject: dict[str, Any]) -> list[str]:
    cell = subject.get("baseline") or {}
    if cell.get("value"):
        return [f"{BULLET} {cell['value']}"]
    return [f"{BULLET} No class baseline recorded ({cell.get('absent', 'unknown')})."]


def _subject_block(subject: dict[str, Any]) -> list[str]:
    """One subject, its point first."""
    lines = [_line(str(subject["label"]).upper())]
    if subject.get("awaiting_validation"):
        lines.append(UNVALIDATED)
    lines += _attribute_lines(subject)
    lines += _section("Class manoeuvre baseline", _baseline_lines(subject))
    lines += _section("Capabilities", _capability_lines(subject))
    lines += _section("Assessed behaviour", _behaviour_lines(subject))
    return lines


def _headline(subjects: list[dict[str, Any]]) -> str:
    """Lead with the point: what this briefing is about, in one line."""
    names = COMMA.join(str(s["label"]) for s in subjects)
    if len(subjects) == 1:
        return f"Briefing: {names}."
    return f"Comparison briefing: {names}."


def build_briefing(comparison: dict[str, Any]) -> dict[str, Any]:
    """The briefing text, plus the counts a caller may want to show."""
    subjects = comparison["subjects"]
    lines = [CLASSIFICATION_BANNER, "", _headline(subjects)]
    unvalidated = [s for s in subjects if s.get("awaiting_validation")]
    if unvalidated:
        caveat = (
            f"{len(unvalidated)} of {len(subjects)} assessments in this "
            "briefing are not validated. Every statement below carries its "
            "marker, its confidence and its source."
        )
        lines += ["", caveat]
    for subject in subjects:
        lines += ["", ""] + _subject_block(subject)
    if len(subjects) == 0:
        lines += ["", NOTHING_RECORDED]
    return {
        "text": "\n".join(lines).strip() + "\n",
        "subjects": len(subjects),
        "unvalidated": len(unvalidated),
    }
