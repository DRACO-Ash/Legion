"""The theatre: every assessed behaviour in the catalogue on one time axis.

The per-object timeline answers "what has this object done". It cannot answer
the question an analyst asks of a theatre: what else was going on at the same
time. Three Shiyan-24C corkscrews and an SJ-6 inspection all recorded in March
2025 is one event seen four times, and nothing in a per-object view says so.

This reuses `build_timeline` for every placement, so the epoch precision rule,
the instant rule and the counterpart resolution are the same code the object
timeline runs, and only the grouping is new.

**Sharing a period is not a relationship, and the overlap rule is narrow on
purpose.** Two behaviours share a period when their recorded dates overlap,
each date widened to the precision it was recorded at: "2025" covers the whole
year, "2025-03" the whole month. A behaviour with no recorded end is counted
only across the period its start names. Counting it to the axis end would turn
a blank field into years of invented co-occurrence, which is the same mistake
as reading a missing end as "ongoing".
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from src.pol import build_timeline

OVERLAP_RULE = (
    "Two behaviours share a period when their recorded dates overlap, each "
    "date widened to the precision it was recorded at. A behaviour with no "
    "recorded end is counted only across the period its start names, never "
    "to the present. Sharing a period is co-occurrence, not a relationship."
)


def _period_end(iso: str, precision: str) -> date:
    """The last day a date recorded at this precision could mean."""
    year, month, day = (int(part) for part in iso.split("-")[:3])
    if precision == "year":
        return date(year, 12, 31)
    if precision == "month":
        return date(year, month, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _extent(segment: dict[str, Any]) -> tuple[date, date]:
    """The recorded extent, never longer than the sources support."""
    start = date.fromisoformat(segment["start"])
    if segment.get("end"):
        return start, _period_end(segment["end"], segment["end_precision"])
    return start, _period_end(segment["start"], segment["start_precision"])


def _mark_shared_periods(segments: list[dict[str, Any]]) -> None:
    """Give each segment the ids of other objects' segments sharing a period.

    Same-object overlaps are left out: an object's own history is what its
    dossier shows, and the theatre is for what other objects were doing.
    """
    extents = {segment["id"]: _extent(segment) for segment in segments}
    for segment in segments:
        lo, hi = extents[segment["id"]]
        segment["shared_period"] = [
            other["id"]
            for other in segments
            if other["subject_id"] != segment["subject_id"]
            and extents[other["id"]][0] <= hi
            and lo <= extents[other["id"]][1]
        ]


def _pct(lo: date, span_days: int, at: date) -> float:
    return round(100.0 * (at - lo).days / span_days, 4)


def _ticks(lo: date, hi: date, span_days: int) -> list[dict[str, Any]]:
    """A labelled mark at the start of each year the axis crosses."""
    return [
        {
            "label": str(year),
            "offset_pct": _pct(lo, span_days, max(lo, date(year, 1, 1))),
        }
        for year in range(lo.year, hi.year + 1)
    ]


def _place_on_axis(placed: list[dict[str, Any]]) -> tuple[date, date, int]:
    """Draw each behaviour as exactly the extent the overlap rule counts.

    The object timeline runs an open-ended band to its axis end. Here that
    would draw years of behaviour nobody recorded, and the picture would then
    disagree with the shared-period list beside it. So a band covers its
    recorded extent and no more, and the axis runs to the end of the latest
    recorded period rather than the latest start, which had put every
    behaviour recorded in March 2025 at zero width on the right edge.
    """
    extents = [_extent(segment) for segment in placed]
    lo = min(start for start, _ in extents)
    hi = max(end for _, end in extents)
    span_days = (hi - lo).days + 1
    for segment, (start, end) in zip(placed, extents, strict=True):
        segment.pop("offset_pct", None)
        segment.pop("width_pct", None)
        segment["extent"] = {"from": start.isoformat(), "to": end.isoformat()}
        segment["x_pct"] = _pct(lo, span_days, start)
        segment["w_pct"] = round(100.0 * ((end - start).days + 1) / span_days, 4)
    return lo, hi, span_days


def _segments_with_subjects(
    records: list[dict[str, Any]], layers: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    found = []
    for record in records:
        if record.get("archived"):
            continue
        layer = layers.get(record["id"]) or {}
        for segment in layer.get("pol_segments", []):
            if segment.get("archived"):
                continue
            found.append(
                {
                    **segment,
                    "subject_id": record["id"],
                    "subject": record.get("catalogue_name"),
                    "nation": record.get("nation"),
                    "family_id": record.get("family_id"),
                    "family_title": record.get("family_title"),
                }
            )
    return found


def _lanes(placed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One lane per family, one row per object, in a fixed reading order."""
    lanes: dict[str, dict[str, Any]] = {}
    for segment in placed:
        lane = lanes.setdefault(
            str(segment["family_id"]),
            {
                "family_id": segment["family_id"],
                "family_title": segment["family_title"],
                "nation": segment["nation"],
                "rows": {},
            },
        )
        row = lane["rows"].setdefault(
            segment["subject_id"],
            {
                "subject_id": segment["subject_id"],
                "subject": segment["subject"],
                "segments": [],
            },
        )
        row["segments"].append(segment)
    ordered = sorted(lanes.values(), key=lambda lane: str(lane["family_title"]))
    for lane in ordered:
        lane["rows"] = sorted(lane["rows"].values(), key=lambda r: str(r["subject"]))
    return ordered


def build_theatre(
    records: list[dict[str, Any]], layers: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Every live behaviour, on one axis, grouped by family."""
    names = {
        record["id"]: record.get("catalogue_name", record["id"]) for record in records
    }
    timeline = build_timeline(_segments_with_subjects(records, layers), names)
    placed = timeline["segments"]
    if not placed:
        return {
            "count": 0,
            "span": None,
            "ticks": [],
            "lanes": [],
            "nations": [],
            "overlap_rule": OVERLAP_RULE,
        }
    _mark_shared_periods(placed)
    lo, hi, span_days = _place_on_axis(placed)
    return {
        "count": len(placed),
        "span": {"from": lo.isoformat(), "to": hi.isoformat()},
        "ticks": _ticks(lo, hi, span_days),
        "lanes": _lanes(placed),
        "nations": sorted({str(segment["nation"]) for segment in placed}),
        "overlap_rule": OVERLAP_RULE,
    }
