"""Reading the CelesTrak satellite catalogue snapshot.

Why this exists: `celestrak.org` and `www.space-track.org` both return 403 at
the organisation proxy, which is a policy denial, so nothing in this
environment can resolve a catalogue number live. Ash supplied a SATCAT
snapshot instead, and it is held in the repository as the reference of record
at `reference/satcat_26195.dat`.

**The column layout below was measured against the supplied file, not read
from a specification.** It matches the shape CelesTrak documents for
`satcat.txt` in the fields that matter, and differs from it in the tail, so
treat the first five as verified against the data and the orbital fields as
INFERENCE until something else needs them. `tests/test_satcat.py` pins the
layout against real rows, so a different snapshot with a different shape
fails rather than parsing into nonsense.

The 9 MB snapshot is deliberately **not** in the upload package. The
container needs the few dozen rows the catalogue actually references, not the
whole thing, and a static snapshot inside a deployed image goes stale with
nobody watching. `scripts/extract_satcat.py` distils it into
`src/satcat_extract.json`, which is what ships. Regenerating that is one
command when a newer snapshot arrives.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# Measured against reference/satcat_26195.dat, half-open [start, end).
FIELDS: dict[str, tuple[int, int]] = {
    "intldes": (0, 11),
    "norad_id": (12, 17),
    "name": (18, 42),
    "source": (43, 47),
    "launch_date": (49, 58),
    "launch_site": (60, 65),
    "decay_date": (67, 76),
}

EXTRACT_PATH = Path(__file__).resolve().parent / "satcat_extract.json"

MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def parse_line(line: str) -> dict[str, str] | None:
    """One SATCAT row, or None if the line is too short to be one.

    A truncated or blank line is skipped rather than yielding a record with
    empty fields, because an empty catalogue number would silently match
    nothing and look like an absent object rather than a broken file.
    """
    if len(line.rstrip("\n")) < FIELDS["launch_date"][1]:
        return None
    record = {name: line[a:b].strip() for name, (a, b) in FIELDS.items()}
    return record if record["norad_id"].isdigit() else None


def read_snapshot(path: Path) -> Iterator[dict[str, str]]:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            record = parse_line(line)
            if record is not None:
                yield record


def launch_year(record: dict[str, str]) -> int | None:
    """The four-digit launch year from a two-digit SATCAT date.

    The snapshot writes "04 OCT 57" and "16 APR 26". The pivot is the space
    age itself: nothing was launched before 1957, so a two-digit year below
    57 is this century and 57 or above is the last one. That is exact for
    every row this file can hold rather than a guess about a window.
    """
    parts = record.get("launch_date", "").split()
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    short = int(parts[2])
    return 2000 + short if short < 57 else 1900 + short


def iso_launch_date(record: dict[str, str]) -> str | None:
    parts = record.get("launch_date", "").split()
    year = launch_year(record)
    if year is None or len(parts) != 3 or parts[1] not in MONTHS:
        return None
    return f"{year:04d}-{MONTHS[parts[1]]:02d}-{int(parts[0]):02d}"


def load_extract() -> dict[str, dict[str, Any]]:
    """The committed subset, keyed by catalogue number.

    Returns an empty mapping if the extract is absent, so the application
    runs without it: it enriches the catalogue, it does not gate it.
    """
    try:
        with open(EXTRACT_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)["objects"]
    except (OSError, json.JSONDecodeError, KeyError):
        return {}
