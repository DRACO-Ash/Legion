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

# The JCO HRR rank band this chart will pull element sets for. Ash's rule, 6
# September 2026: rank 4 and 5 entries have proved unreliable enough that
# pulling their history risks putting a wrong line on the chart, and a wrong
# line is worse than a missing one. An object with no rank at all - absent
# from the feed for the window - is not pulled either, because "only ranks 0
# to 3" cannot be satisfied for an object that has no rank. Both cases are
# listed under the chart rather than dropped silently.
ALLOWED_HRR_RANKS = frozenset({0, 1, 2, 3})

# window_days sentinel: no lower epoch bound, so UDL returns everything it
# holds for the satellite.
FULL_HISTORY = 0

# A full history can run to thousands of element sets. Every one of them is
# fetched and every one is used for the drift rate, but the series returned is
# thinned to this many evenly spaced points, first and last always kept: past
# roughly a thousand points a line is drawing more marks than the plot has
# pixels, and the browser pays for all of them. The count it was thinned from
# travels with the series so the chart can say so.
MAX_POINTS_PER_SERIES = 1000

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
SKIP_RANK_OUTSIDE_BAND = "JCO HRR rank {rank}, outside the 0-3 band"
SKIP_NOT_IN_HRR_FEED = "Not in the JCO HRR feed for this window, so carries no rank"
NOTE_THINNED = "Plotting {shown} of {total} element sets, evenly spaced"

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
    """Bound the requested window, with zero reserved for the full history.

    A negative value is a typo, not a request for everything, so it clamps to
    the minimum rather than opening the tap.
    """
    if requested is None:
        return DEFAULT_WINDOW_DAYS
    if requested == FULL_HISTORY:
        return FULL_HISTORY
    return max(MIN_WINDOW_DAYS, min(MAX_WINDOW_DAYS, requested))


def _as_rank(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def hrr_ranks(client: Any, cache: Any, window_hours: int) -> dict[str, int]:
    """satNo to JCO HRR rank, for every satellite in the feed's window.

    Fetched once per request and cached, because the feed is one call that
    answers the rank question for every satellite at once.

    A failure here is not survivable and is deliberately not swallowed: the
    rank band is a data-quality gate, and pulling element sets with the gate
    silently open would produce exactly the chart the gate exists to prevent.
    """
    key = f"jco-hrr-ranks:{window_hours}"
    cached = cache.get(key) if cache is not None else None
    if cached is not None:
        return cached

    ranks: dict[str, int] = {}
    for entry in await client.fetch_jco_hrr(window_hours=window_hours):
        sat_no = entry.get("satNo")
        rank = _as_rank(entry.get("rank"))
        if sat_no is not None and rank is not None:
            ranks[str(sat_no)] = rank

    if cache is not None:
        cache.set(key, ranks)
    return ranks


def thin(values: list[Any], limit: int) -> list[Any]:
    """Evenly spaced sample, first and last always kept."""
    if len(values) <= limit:
        return values
    last = len(values) - 1
    indices = sorted({round(i * last / (limit - 1)) for i in range(limit)})
    return [values[i] for i in indices]


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


def _plot_points(
    readings: list[tuple[dt.datetime, dict[str, Any]]], metric: str
) -> tuple[list[ElementPoint], list[tuple[dt.datetime, float]]]:
    """Element sets reduced to the plotted metric, dropping any that lack it."""
    points: list[ElementPoint] = []
    numeric: list[tuple[dt.datetime, float]] = []
    for epoch, record in readings:
        value = _value_for(metric, epoch, record)
        if value is None:
            continue
        points.append(ElementPoint(epoch=epoch.isoformat(), value=value))
        numeric.append((epoch, value))
    return points, numeric


def _fetch_note(
    records: list[dict[str, Any]], points: list[ElementPoint], source: str
) -> str | None:
    """What to say beside a satellite's name about the data behind its line."""
    if not records:
        return NOTE_NO_ELEMENT_SET
    if not points:
        return NOTE_NO_USABLE_POINTS
    if source == SOURCE_LATEST:
        return NOTE_LATEST_ONLY
    return None


def _joined(first: str | None, second: str | None) -> str | None:
    if first and second:
        return f"{first}. {second}"
    return first or second


def build_series(
    member: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    source: str,
    colour_index: int,
    hrr_rank: int | None = None,
    note: str | None = None,
) -> tuple[str, FamilySeries]:
    """Reduce one satellite's element sets to a single plotted metric."""
    readings = _readings(records)
    latest_mean_motion = (
        _as_float(readings[-1][1].get("meanMotion")) if readings else None
    )
    metric = metric_for(member.get("regime"), latest_mean_motion)
    points, numeric = _plot_points(readings, metric)

    # Drift is measured across the whole history, then the series is thinned
    # for the plot. Thinning after the measurement keeps a long history's
    # answer exact rather than an artefact of which points survived.
    drift = (
        drift_rate_degrees_per_day(numeric) if metric == METRIC_MEAN_LONGITUDE else None
    )
    total_points = len(points)
    plotted = thin(points, MAX_POINTS_PER_SERIES)
    thinned_note = (
        NOTE_THINNED.format(shown=len(plotted), total=total_points)
        if len(plotted) < total_points
        else None
    )

    series = FamilySeries(
        catalogue_name=str(member.get("catalogue_name") or ""),
        norad_id=str(member.get("norad_id") or ""),
        regime=str(member.get("regime") or ""),
        status=str(member.get("status") or "unknown"),
        archived=bool(member.get("archived")),
        colour_index=colour_index,
        source=source,
        points=plotted,
        latest_value=numeric[-1][1] if numeric else None,
        drift_deg_per_day=drift,
        hrr_rank=hrr_rank,
        point_count=total_points,
        note=_joined(note or _fetch_note(records, points, source), thinned_note),
    )
    return metric, series


async def _fetch_records(
    client: Any, cache: Any, sat_no: str, window_days: int, since: dt.datetime | None
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


def _skip_reason(
    member: dict[str, Any], rank: int | None, charted_so_far: int
) -> str | None:
    """Why this member is not charted, or None if it is.

    The order matters: a member is reported against the first gate it fails,
    which is the one an analyst can act on.
    """
    if not member.get("norad_id"):
        return SKIP_NO_NORAD_ID
    if rank is None:
        return SKIP_NOT_IN_HRR_FEED
    if rank not in ALLOWED_HRR_RANKS:
        return SKIP_RANK_OUTSIDE_BAND.format(rank=rank)
    if charted_so_far >= MAX_SERIES:
        return SKIP_OVER_PALETTE_LIMIT
    return None


def partition_members(
    members: list[dict[str, Any]], ranks: dict[str, int]
) -> tuple[list[tuple[int, dict[str, Any], int]], list[FamilyMemberSkipped]]:
    """Split a family into what will be charted and what will not.

    The index carried alongside each eligible member is its position in the
    whole family, which becomes its colour: a satellite keeps its colour
    whoever else is excluded.
    """
    eligible: list[tuple[int, dict[str, Any], int]] = []
    skipped: list[FamilyMemberSkipped] = []
    for index, member in enumerate(order_members(members)):
        rank = ranks.get(str(member.get("norad_id") or ""))
        reason = _skip_reason(member, rank, len(eligible))
        if reason is not None:
            skipped.append(
                FamilyMemberSkipped(
                    catalogue_name=str(member.get("catalogue_name") or ""),
                    reason=reason,
                )
            )
        elif rank is not None:
            eligible.append((index, member, rank))
    return eligible, skipped


def _charts_from(grouped: dict[str, list[FamilySeries]]) -> list[FamilyChart]:
    """One chart per metric present, longitude first."""
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
    return charts


def _overall_source(sources: set[str]) -> str:
    """How deep the data behind this family is, in one word.

    Mixed is its own answer rather than the more flattering of the two: a
    family where one satellite has years of history and another has a single
    element set is not uniform, and the chart should not imply it is.
    """
    if len(sources) > 1:
        return SOURCE_MIXED
    if sources:
        return next(iter(sources))
    return SOURCE_NONE


async def build_family_charts(
    *,
    client: Any,
    cache: Any,
    family_id: str,
    family_title: str,
    members: list[dict[str, Any]],
    window_days: int,
    hrr_window_hours: int,
    now: dt.datetime | None = None,
) -> FamilyElementsResponse:
    """Fetch and assemble every chart for one family.

    Membership comes from the catalogue, which is what makes these objects
    Red. Whether an object is pulled at all comes from its JCO HRR rank: only
    ranks 0 to 3, one feed call for the whole family. Everything else is
    listed under the chart with the rank that excluded it.

    A single satellite failing costs that satellite's line and a note beside
    its name, not the whole chart. Every satellite failing raises, because that
    is an outage rather than a gap and the analyst should be told so.
    """
    now = now or dt.datetime.now(dt.UTC)
    since = (
        None if window_days == FULL_HISTORY else now - dt.timedelta(days=window_days)
    )
    ranks = await hrr_ranks(client, cache, hrr_window_hours)
    eligible, skipped = partition_members(members, ranks)

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

    fetched = await asyncio.gather(*(fetch(member) for _, member, _rank in eligible))
    failures = [result for result in fetched if result[2] == NOTE_UDL_FAILED]
    if eligible and len(failures) == len(fetched):
        raise UDLError("Every element-set lookup in this family failed")

    grouped: dict[str, list[FamilySeries]] = {}
    sources: set[str] = set()
    for (colour_index, member, rank), (records, source, note) in zip(
        eligible, fetched, strict=True
    ):
        metric, series = build_series(
            member,
            records,
            source=source,
            colour_index=colour_index,
            hrr_rank=rank,
            note=note,
        )
        grouped.setdefault(metric, []).append(series)
        sources.update({source} & {SOURCE_HISTORY, SOURCE_LATEST})

    charts = _charts_from(grouped)
    overall = _overall_source(sources)

    return FamilyElementsResponse(
        family_id=family_id,
        family_title=family_title,
        window_days=window_days,
        generated_at=now.isoformat(),
        source=overall,
        charts=charts,
        skipped=skipped,
    )
