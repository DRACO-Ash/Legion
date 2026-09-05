"""Assembles a family's element-set history into chart-ready series.

The question this answers is the one an analyst actually asks of a class of
satellites: are they holding station, drifting, or closing on each other? One
satellite's element set says almost nothing; the family's, plotted together on
one axis, is where a pattern shows.

Two rules shape everything below.

One axis per metric. A GEO object is charted on mean longitude and a LEO
object on mean motion, and those never share a plot: two y-scales on one chart
invent a correlation that is not in the data. A family holding both kinds of
object therefore produces two charts, not one chart with two axes.

Colour follows the entity. A satellite's colour index comes from its position
in the family's stable member ordering, fixed before anything is filtered or
split, so a satellite keeps its colour whichever chart it lands in and however
the catalogue is filtered.

Nothing here calls UDL directly: the client is injected, which is what lets
the whole path be tested without a network.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any

from src.models import (
    ElementPoint,
    FamilyChart,
    FamilyElementsResponse,
    FamilyMemberSkipped,
    FamilySeries,
)
from src.orbits import (
    METRIC_MEAN_LONGITUDE,
    METRIC_MEAN_MOTION,
    drift_rate_degrees_per_day,
    mean_longitude_degrees,
    metric_for,
    parse_epoch,
)
from src.udl_client import UDLError

logger = logging.getLogger("udl_tactics_app.family_elements")

DEFAULT_WINDOW_DAYS = 30
MIN_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 180

# The categorical palette has eight slots and they are never cycled: a ninth
# colour would be indistinguishable from one already on the chart under
# colour-vision deficiency. Nine members in one family means the ninth is
# listed as skipped rather than quietly given a duplicate colour. The largest
# seeded family today has eight.
MAX_SERIES = 8

# One family fans out to one UDL call per member. Four at a time keeps a chart
# responsive without turning a page load into a burst against a shared UDL
# account.
MAX_CONCURRENT_FETCHES = 4

CACHE_TTL_SECONDS = 120.0

SOURCE_HISTORY = "elset-history"
SOURCE_LATEST = "elset-latest"
SOURCE_MIXED = "mixed"
SOURCE_NONE = "none"

NOTE_NO_ELEMENT_SET = "UDL holds no element set for this satNo"
NOTE_UDL_FAILED = "UDL did not answer for this satNo"
NOTE_LATEST_ONLY = "History unavailable: showing the latest element set only"
NOTE_NO_USABLE_POINTS = (
    "Element sets returned, but none carried the fields this chart needs"
)
SKIP_NO_NORAD_ID = "No NORAD ID on the catalogue record"
SKIP_OVER_PALETTE_LIMIT = f"Beyond the {MAX_SERIES}-series limit for one chart"

_CHART_META = {
    METRIC_MEAN_LONGITUDE: (
        "Mean longitude",
        "°E",
        (
            "Approximate sub-satellite longitude derived from the element set, "
            "east positive. Meaningful for near-geosynchronous objects only, "
            "and an approximation: good for drift and station-keeping, not for "
            "conjunction assessment."
        ),
    ),
    METRIC_MEAN_MOTION: (
        "Mean motion",
        "rev/day",
        (
            "Revolutions per day as reported by UDL. A step change is an orbit "
            "change; a steady slope is decay."
        ),
    ),
}

# Longitude first: for these families the GEO picture is the headline.
_METRIC_ORDER = (METRIC_MEAN_LONGITUDE, METRIC_MEAN_MOTION)


def clamp_window_days(requested: int | None) -> int:
    if requested is None:
        return DEFAULT_WINDOW_DAYS
    return max(MIN_WINDOW_DAYS, min(MAX_WINDOW_DAYS, requested))


def order_members(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable, analyst-readable member order: oldest launch first.

    This ordering is what colour assignment hangs off, so it must not depend
    on the catalogue filter, the fetch order, or which members returned data.
    """
    return sorted(
        members,
        key=lambda m: (m.get("launch_year") or 0, str(m.get("catalogue_name") or "")),
    )


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _readings(
    records: list[dict[str, Any]],
) -> list[tuple[dt.datetime, dict[str, Any]]]:
    """Element sets with a parsable epoch, oldest first."""
    dated = [
        (parse_epoch(record.get("epoch")), record)
        for record in records
        if isinstance(record, dict)
    ]
    return sorted(
        ((epoch, record) for epoch, record in dated if epoch is not None),
        key=lambda pair: pair[0],
    )


def _value_for(metric: str, epoch: dt.datetime, record: dict[str, Any]) -> float | None:
    if metric == METRIC_MEAN_MOTION:
        return _as_float(record.get("meanMotion"))
    return mean_longitude_degrees(
        raan=_as_float(record.get("raan")),
        arg_of_perigee=_as_float(record.get("argOfPerigee")),
        mean_anomaly=_as_float(record.get("meanAnomaly")),
        epoch=epoch,
    )


def build_series(
    member: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    source: str,
    colour_index: int,
    note: str | None = None,
) -> tuple[str, FamilySeries]:
    """Reduce one satellite's element sets to a single plotted metric."""
    readings = _readings(records)
    latest_mean_motion = (
        _as_float(readings[-1][1].get("meanMotion")) if readings else None
    )
    metric = metric_for(member.get("regime"), latest_mean_motion)

    points: list[ElementPoint] = []
    numeric: list[tuple[dt.datetime, float]] = []
    for epoch, record in readings:
        value = _value_for(metric, epoch, record)
        if value is None:
            continue
        points.append(ElementPoint(epoch=epoch.isoformat(), value=value))
        numeric.append((epoch, value))

    if note is None:
        if not records:
            note = NOTE_NO_ELEMENT_SET
        elif not points:
            note = NOTE_NO_USABLE_POINTS
        elif source == SOURCE_LATEST:
            note = NOTE_LATEST_ONLY

    drift = (
        drift_rate_degrees_per_day(numeric) if metric == METRIC_MEAN_LONGITUDE else None
    )
    series = FamilySeries(
        catalogue_name=str(member.get("catalogue_name") or ""),
        norad_id=str(member.get("norad_id") or ""),
        regime=str(member.get("regime") or ""),
        status=str(member.get("status") or "unknown"),
        archived=bool(member.get("archived")),
        colour_index=colour_index,
        source=source,
        points=points,
        latest_value=numeric[-1][1] if numeric else None,
        drift_deg_per_day=drift,
        note=note,
    )
    return metric, series


async def _fetch_records(
    client: Any, cache: Any, sat_no: str, window_days: int, since: dt.datetime
) -> tuple[list[dict[str, Any]], str]:
    """One satellite's element sets, from the cache when it is still warm.

    Falls back to the single latest element set when history is unavailable,
    which turns "no chart at all" into "one point per satellite" - still enough
    to show where a class is sitting relative to itself.
    """
    key = f"{sat_no}:{window_days}"
    cached = cache.get(key) if cache is not None else None
    if cached is not None:
        return cached

    history = await client.get_elset_history(sat_no, since=since)
    if history is None:
        latest = await client.get_elset(sat_no)
        result = ([latest] if latest else [], SOURCE_LATEST)
    else:
        result = (history, SOURCE_HISTORY)

    if cache is not None:
        cache.set(key, result)
    return result


async def build_family_charts(
    *,
    client: Any,
    cache: Any,
    family_id: str,
    family_title: str,
    members: list[dict[str, Any]],
    window_days: int,
    now: dt.datetime | None = None,
) -> FamilyElementsResponse:
    """Fetch and assemble every chart for one family.

    A single satellite failing costs that satellite's line and a note beside
    its name, not the whole chart. Every satellite failing raises, because that
    is an outage rather than a gap and the analyst should be told so.
    """
    now = now or dt.datetime.now(dt.UTC)
    since = now - dt.timedelta(days=window_days)
    ordered = order_members(members)

    skipped: list[FamilyMemberSkipped] = []
    eligible: list[tuple[int, dict[str, Any]]] = []
    for index, member in enumerate(ordered):
        name = str(member.get("catalogue_name") or "")
        if not member.get("norad_id"):
            skipped.append(
                FamilyMemberSkipped(catalogue_name=name, reason=SKIP_NO_NORAD_ID)
            )
        elif len(eligible) >= MAX_SERIES:
            skipped.append(
                FamilyMemberSkipped(catalogue_name=name, reason=SKIP_OVER_PALETTE_LIMIT)
            )
        else:
            eligible.append((index, member))

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

    async def fetch(
        member: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], str, str | None]:
        async with semaphore:
            try:
                records, source = await _fetch_records(
                    client, cache, str(member["norad_id"]), window_days, since
                )
            except UDLError:
                logger.warning(
                    "UDL lookup failed for satNo %s in family %s",
                    member.get("norad_id"),
                    family_id,
                )
                return [], SOURCE_NONE, NOTE_UDL_FAILED
            return records, source, None

    fetched = await asyncio.gather(*(fetch(member) for _, member in eligible))

    if eligible and all(result[2] == NOTE_UDL_FAILED for result in fetched):
        raise UDLError("Every element-set lookup in this family failed")

    grouped: dict[str, list[FamilySeries]] = {}
    sources: set[str] = set()
    for (colour_index, member), (records, source, note) in zip(
        eligible, fetched, strict=True
    ):
        metric, series = build_series(
            member,
            records,
            source=source,
            colour_index=colour_index,
            note=note,
        )
        grouped.setdefault(metric, []).append(series)
        if source in (SOURCE_HISTORY, SOURCE_LATEST):
            sources.add(source)

    charts = []
    for metric in _METRIC_ORDER:
        series_list = grouped.get(metric)
        if not series_list:
            continue
        title, unit, description = _CHART_META[metric]
        charts.append(
            FamilyChart(
                metric=metric,
                title=title,
                unit=unit,
                description=description,
                series=series_list,
            )
        )

    if len(sources) > 1:
        overall = SOURCE_MIXED
    elif sources:
        overall = sources.pop()
    else:
        overall = SOURCE_NONE

    return FamilyElementsResponse(
        family_id=family_id,
        family_title=family_title,
        window_days=window_days,
        generated_at=now.isoformat(),
        source=overall,
        charts=charts,
        skipped=skipped,
    )
