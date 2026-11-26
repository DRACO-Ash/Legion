"""CLAUDE.md is the short rules; docs/PROJECT-RECORD.md is the account behind
them. Every rule points to its section by heading, in square brackets, and a
pointer to a heading that does not exist sends the reader nowhere at the one
moment they need the history. These hold the two documents together.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
RECORD = (ROOT / "docs" / "PROJECT-RECORD.md").read_text(encoding="utf-8")

# Brackets that are not section pointers.
NOT_POINTERS = {"DECISION - Ash"}


def _pointers() -> set[str]:
    prose = re.sub(r"`[^`\n]*`", "", RULES)  # a selector in code is not a pointer
    return set(re.findall(r"\[([^\]\n]+)\](?!\()", prose)) - NOT_POINTERS


def _headings() -> list[str]:
    return re.findall(r"^## (.+)$", RECORD, re.MULTILINE)


def test_the_rules_point_to_the_record_at_all():
    assert len(_pointers()) >= 10


def test_every_pointer_names_a_section_of_the_record():
    headings = _headings()
    missing = sorted(
        p for p in _pointers() if not any(h.startswith(p) for h in headings)
    )
    assert missing == [], f"CLAUDE.md points to sections the record lacks: {missing}"


def test_the_code_quality_heading_scripts_cite_still_exists():
    """bump_version.sh and package.sh send the reader to this heading by name."""
    assert "## The Code Quality gate has five conditions, not one" in RULES
