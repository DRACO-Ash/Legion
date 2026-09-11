#!/usr/bin/env python3
"""Distil the SATCAT snapshot into the rows Legion actually references.

Run after replacing `reference/satcat_26195.dat` with a newer snapshot:

    python scripts/extract_satcat.py

Writes `src/satcat_extract.json`, which is what ships. The full 9 MB
snapshot stays out of the upload package: the container needs a few dozen
rows, and a static catalogue inside a deployed image goes stale unwatched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.candidate_systems import CANDIDATE_RECORDS  # noqa: E402
from src.satcat import EXTRACT_PATH, iso_launch_date, launch_year, read_snapshot  # noqa: E402
from src.seed_data import SEED_RECORDS  # noqa: E402

SNAPSHOT = ROOT / "reference" / "satcat_26195.dat"


def wanted_ids() -> set[str]:
    ids = {str(r["norad_id"]) for r in SEED_RECORDS if r.get("norad_id")}
    ids |= {str(r["norad_id"]) for r in CANDIDATE_RECORDS if r.get("norad_id")}
    return ids


def main() -> int:
    if not SNAPSHOT.exists():
        print(f"No snapshot at {SNAPSHOT}", file=sys.stderr)
        return 1
    wanted = wanted_ids()
    found = {}
    for record in read_snapshot(SNAPSHOT):
        if record["norad_id"] in wanted:
            found[record["norad_id"]] = {
                **record,
                "launch_year": launch_year(record),
                "launch_date_iso": iso_launch_date(record),
            }
    payload = {
        "source": SNAPSHOT.name,
        "count": len(found),
        "objects": dict(sorted(found.items(), key=lambda kv: int(kv[0]))),
    }
    EXTRACT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    missing = sorted(wanted - set(found), key=int)
    print(f"Wrote {len(found)} of {len(wanted)} referenced objects to {EXTRACT_PATH}")
    if missing:
        print(f"Not in this snapshot: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
