"""The pattern-of-life mode vocabulary, in words, served to the interface.

Same rule as `provenance.py`, for the same reason. The interface must not
hold its own copy of what `rpo_corkscrew` means, or of which modes are
instants rather than spans: a hard-coded copy would drift from the validators
that enforce the same vocabulary, and nothing would fail. This project has
now had several bugs where the browser described something it could not see.

So the labels, the meanings and the two structural properties live here,
beside the model that uses them, and `GET /api/pol/modes` serves them. The
interface owns only how a band and a node are drawn.

Two properties are structural rather than cosmetic:

● `instantaneous` says draw a marker, not a band. A separation is a point in
  time, and giving it a width invents a duration the data does not have.
● `needs_counterpart` says the mode is meaningless alone. An RPO is always
  with something, and that counterpart drives the relative-motion view.

Both are read from the model's own frozensets rather than restated here, so
adding a mode to one cannot leave the other behind.
"""

from datetime import date
from typing import Any, get_args

from src.compendium_models import (
    INSTANTANEOUS_MODES,
    MODES_NEEDING_COUNTERPART,
    BehaviourMode,
    Observability,
)

MODE_LABELS: dict[str, str] = {
    "station_keeping": "Station keeping",
    "longitudinal_drift": "Longitudinal drift",
    "rpo_inspection": "RPO, inspection",
    "rpo_shadowing": "RPO, shadowing",
    "rpo_corkscrew": "RPO, corkscrew",
    "rpo_docking": "RPO, docking",
    "pursuit": "Pursuit",
    "retirement": "Retirement",
    "separation_event": "Separation event",
    "anomalous_high_dv": "Anomalous high delta-v",
    "quiescent": "Quiescent",
    "unknown": "Unknown",
}

MODE_MEANINGS: dict[str, str] = {
    "station_keeping": (
        "Small periodic corrections holding a slot. The GEO baseline is "
        "0.5 to 1 m/s, and the anomaly is the deviation from it."
    ),
    "longitudinal_drift": "Walking the belt at a steady rate in degrees per day.",
    "rpo_inspection": "Closing on another object to observe it.",
    "rpo_shadowing": "Matching plane and loitering alongside, a co-planar shadow.",
    "rpo_corkscrew": (
        "Walking or corkscrewing around another object. The profile a senior "
        "US Space Force official publicly called dogfighting in March 2025."
    ),
    "rpo_docking": "Docking with or capturing another object.",
    "pursuit": "Actively chasing an object that is itself manoeuvring.",
    "retirement": "Raising to a graveyard orbit, roughly 300 km above the belt.",
    "separation_event": "Releasing a sub-object. An instant, not a span.",
    "anomalous_high_dv": (
        "A manoeuvre far outside the class baseline. An instant, not a span."
    ),
    "quiescent": "On orbit with no significant manoeuvre.",
    "unknown": "Not assessed. Shown so a gap in the timeline is visible as a gap.",
}

OBSERVABILITY_MEANINGS: dict[str, str] = {
    "dense": "Frequent revisits and good sensor coverage across the segment.",
    "moderate": "Enough coverage to characterise the mode, with gaps.",
    "sparse": "Thin coverage. The mode is an interpretation of few points.",
    "unknown": "Coverage not assessed.",
}


def _mode_entry(value: str) -> dict[str, Any]:
    return {
        "value": value,
        "label": MODE_LABELS[value],
        "meaning": MODE_MEANINGS[value],
        "instantaneous": value in INSTANTANEOUS_MODES,
        "needs_counterpart": value in MODES_NEEDING_COUNTERPART,
    }


def modes() -> dict[str, Any]:
    """Everything the interface needs to draw and explain a timeline.

    Observability is served alongside, and separately, because it answers a
    different question from confidence: how well the behaviour could actually
    be seen, not how sure we are the assessment is right. A segment from a
    sparse track and one from a dense track must never render identically.
    """
    return {
        "modes": [_mode_entry(value) for value in get_args(BehaviourMode)],
        "observability": [
            {"value": value, "meaning": OBSERVABILITY_MEANINGS[value]}
            for value in get_args(Observability)
        ],
    }


EPOCH_PRECISION = {4: "year", 7: "month", 10: "day"}


def parse_pol_epoch(epoch: str) -> tuple[str, str]:
    """A sourced epoch and the precision it actually carries.

    Returns the ISO date to place it on and the precision that produced it.
    A source saying "May 2024" supports `2024-05` and nothing finer, so the
    segment stores `2024-05` and the timeline is told the precision rather
    than left to infer a day that nobody observed. The interface says which
    it has; a month-precision band drawn as if it were day-precision is the
    same class of error as promoting an inference to a fact.

    Anything else is returned unchanged with precision "unrecognised", so a
    hand-entered epoch is visibly odd rather than silently coerced.
    """
    text = (epoch or "").strip()
    precision = EPOCH_PRECISION.get(len(text))
    if precision is None or not _is_iso_prefix(text, len(text)):
        return text, "unrecognised"
    padding = {"year": "-01-01", "month": "-01", "day": ""}[precision]
    return text + padding, precision


def _is_iso_prefix(text: str, length: int) -> bool:
    parts = text.split("-")
    expected = {4: 1, 7: 2, 10: 3}[length]
    return len(parts) == expected and all(part.isdigit() for part in parts)


OPEN_ENDED = "open"
INSTANT = "instant"
TARGET_PREFIX = "target:"


def counterpart(related_id: str | None, names: dict[str, str]) -> dict[str, Any] | None:
    """The counterpart as a person reads it, resolved here not in the browser.

    The interface only ever holds the page of the catalogue it is showing, so
    a client-side lookup renders a raw uuid the moment a filter hides the
    other object. Found in a browser, which is the only way any of this
    interface's naming bugs have ever been found.

    An unheld counterpart keeps its slug and is marked as outside the
    catalogue, because pretending USA 314 is one of our systems would put a
    phantom object in front of an analyst.
    """
    if not related_id:
        return None
    if related_id.startswith(TARGET_PREFIX):
        slug = related_id[len(TARGET_PREFIX) :].replace("-", " ")
        return {"id": related_id, "label": slug, "in_catalogue": False}
    return {
        "id": related_id,
        "label": names.get(related_id, related_id),
        "in_catalogue": related_id in names,
    }


def build_timeline(
    segments: list[dict[str, Any]], names: dict[str, str] | None = None
) -> dict[str, Any]:
    """Place an object's segments on one axis, sorted, with their precision.

    The span runs from the earliest start to the latest end. A segment with
    no recorded end runs to the axis end and is flagged `open` rather than
    given an invented finish, and the interface says "no end recorded"
    rather than "ongoing": a blank field is not evidence that a behaviour
    continues. A single-instant history, or one where everything
    shares a date, would divide by zero, so the axis is widened rather than
    collapsed: one point still has to be placeable.
    """
    placed = [_place(segment, names or {}) for segment in segments]
    placed = [entry for entry in placed if entry["start"]]
    if not placed:
        return {"count": 0, "span": None, "segments": []}

    starts = [entry["start"] for entry in placed]
    ends = [entry["end"] or entry["start"] for entry in placed]
    first, last = min(starts), max(ends)
    if first == last:
        last = first[:4] + "-12-31" if len(first) >= 4 else last

    for entry in placed:
        entry["offset_pct"] = _fraction(first, last, entry["start"])
        finish = entry["end"] or last
        entry["width_pct"] = max(
            0.0, _fraction(first, last, finish) - entry["offset_pct"]
        )
    placed.sort(key=lambda entry: (entry["start"], entry["mode"]))
    return {
        "count": len(placed),
        "span": {"from": first, "to": last},
        "segments": placed,
    }


def _place(segment: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    start, start_precision = parse_pol_epoch(str(segment.get("start_epoch") or ""))
    mode = str(segment.get("mode"))
    instantaneous = mode in INSTANTANEOUS_MODES
    end, end_precision = _end_of(segment, instantaneous)
    return {
        **segment,
        "start": start if start_precision != "unrecognised" else "",
        "end": end,
        "start_precision": start_precision,
        "end_precision": end_precision,
        "instantaneous": instantaneous,
        "mode_label": MODE_LABELS.get(mode, mode),
        "counterpart": counterpart(segment.get("related_object_id"), names),
    }


def _end_of(segment: dict[str, Any], instantaneous: bool) -> tuple[str | None, str]:
    """An instant has no end, and an absent end is not a continuing behaviour.

    Two mistakes, both caught in a browser. A separation or an anomalous
    burn is a point in time, so "2024 to ongoing" on the TJS-2 node asserted
    a behaviour that is still happening. And SJ-21's 2022 capture, which is
    finished, read as ongoing purely because no end was recorded.

    So an absent end means exactly that: no end recorded. Where a source
    does say a behaviour continues, as it does for COSMOS-2558, that belongs
    in the claim, which is a sourced statement, rather than being inferred
    from a blank field.
    """
    if instantaneous:
        return None, INSTANT
    raw_end = segment.get("end_epoch")
    if not raw_end:
        return None, OPEN_ENDED
    end, precision = parse_pol_epoch(str(raw_end))
    return (end if precision != "unrecognised" else None), precision


def _fraction(first: str, last: str, point: str) -> float:
    lo, hi, at = (_ordinal(value) for value in (first, last, point))
    if hi <= lo:
        return 0.0
    return round(100.0 * (at - lo) / (hi - lo), 4)


def _ordinal(iso: str) -> int:
    """Days since year zero, from a full ISO date. Stdlib only, like orbits.py."""
    year, month, day = (int(part) for part in iso.split("-")[:3])
    return date(year, month, day).toordinal()
