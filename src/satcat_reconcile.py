"""Check the catalogue against the SATCAT snapshot, and say what disagrees.

The point of holding a catalogue snapshot is not that it sits there. It is
that a catalogue number in this application can be wrong in a way nothing
else catches: a wrong number plots a real satellite's element sets under
another satellite's name, and every chart looks entirely normal.

So this compares what the store holds with what the snapshot says, and
reports three kinds of disagreement:

● **`unknown`** -- the number is not in the snapshot at all. Expected for
  anything launched after it was taken, so the snapshot's own name is
  reported alongside for a reader to judge.
● **`name`** -- the number exists and names a different object. This is the
  serious one.
● **`shared`** -- two or more catalogue records claim one number. At most one
  of them can be right.

It reports rather than corrects. `src/seed_data.py` is a verbatim mirror of a
delivered spreadsheet and the standing rule is that its values are not
re-derived here, so a disagreement is put in front of the person who owns
that source instead of being quietly patched out of sight.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from src.satcat import load_extract

SPACE = " "
UNKNOWN = "unknown"
NAME = "name"
SHARED = "shared"

_PUNCTUATION = re.compile(r"[^A-Z0-9]+")
# SATCAT writes "SHIJIAN 6 05A (SJ-6 05A)"; the catalogue writes "SJ-6-05A".
# Both spellings are compared, so a house abbreviation is not a discrepancy.
_ALIASES = {"SHIJIAN": "SJ", "SHIYAN": "SY", "COSMOS": "COSMOS"}


def _tokens(name: str) -> set[str]:
    """Every spelling of a name, punctuation-flattened.

    A SATCAT row carries the long form and the short form together, so both
    are kept: matching either is a match. Without this the whole SJ and SY
    catalogue reads as mismatched and the report becomes noise nobody looks
    at, which is worse than no report.
    """
    flattened = _PUNCTUATION.sub(SPACE, name.upper()).strip()
    words = [_ALIASES.get(word, word) for word in flattened.split()]
    expanded = SPACE.join(words)
    # A third, space-free spelling, because the snapshot writes
    # "PRC TEST SPACECRAFT2" where the catalogue writes "PRC Test
    # Spacecraft 2". One missing space is not a discrepancy, and a report
    # full of non-discrepancies is a report nobody reads.
    return {
        expanded,
        flattened,
        expanded.replace(SPACE, ""),
        flattened.replace(SPACE, ""),
    }


def _names_agree(catalogue_name: str, satcat_name: str) -> bool:
    ours = _tokens(catalogue_name)
    theirs = _tokens(satcat_name)
    return any(a in b or b in a for a in ours for b in theirs)


def _shared_numbers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_number: dict[str, list[str]] = defaultdict(list)
    for record in records:
        number = str(record.get("norad_id") or "")
        if number:
            by_number[number].append(str(record.get("catalogue_name")))
    return [
        {"kind": SHARED, "norad_id": number, "claimed_by": sorted(names)}
        for number, names in sorted(by_number.items())
        if len(names) > 1
    ]


def reconcile(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Every disagreement between the catalogue and the snapshot."""
    snapshot = load_extract()
    findings: list[dict[str, Any]] = []
    checked = 0
    for record in records:
        number = str(record.get("norad_id") or "")
        if not number:
            continue
        checked += 1
        name = str(record.get("catalogue_name"))
        row = snapshot.get(number)
        if row is None:
            findings.append(
                {"kind": UNKNOWN, "norad_id": number, "catalogue_name": name}
            )
        elif not _names_agree(name, row["name"]):
            findings.append(
                {
                    "kind": NAME,
                    "norad_id": number,
                    "catalogue_name": name,
                    "satcat_name": row["name"],
                    "satcat_launch": row.get("launch_date_iso"),
                }
            )
    findings.extend(_shared_numbers(records))
    return {
        "checked": checked,
        "snapshot_objects": len(snapshot),
        "count": len(findings),
        "findings": findings,
    }
