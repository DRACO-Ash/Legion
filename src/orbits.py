"""Orbital derivations for the family movement charts.

Pure functions, standard library only. Nothing here talks to UDL or to the
store, so every value below is testable against a published reference rather
than against a live pull.

What this exists for: UDL's element set carries no longitude field. For a
near-geosynchronous object the sub-satellite longitude is the classical mean
longitude,

    lambda = RAAN + argOfPerigee + meanAnomaly - GMST(epoch)

which is an APPROXIMATION, not a fact taken from UDL: it holds for small
eccentricity and small inclination, which is what a GEO station-keeping box
means in practice, and degrades as either grows. It is good enough to show a
class drifting, holding station, or closing on a neighbour - which is the
question the chart answers - and it is not good enough for a conjunction
assessment. The UI says so next to the axis.

Mean motion needs no derivation: UDL reports it directly in revolutions per
day, and for a LEO object it is the cleanest single number for "has this
thing changed its orbit".
"""

from __future__ import annotations

import datetime as dt
import math

# JD of the Unix epoch, 1970-01-01T00:00:00Z. FACT, standard constant.
JULIAN_DATE_AT_UNIX_EPOCH = 2440587.5
SECONDS_PER_DAY = 86400.0

# J2000.0 = 2000-01-01T12:00:00 TT, JD 2451545.0. FACT, standard constant.
J2000_JULIAN_DATE = 2451545.0
JULIAN_CENTURY_DAYS = 36525.0

# IAU 1982 GMST, in the degrees-and-Julian-centuries form (Meeus, Astronomical
# Algorithms, 2nd ed., eq. 12.4). FACT, published coefficients.
GMST_AT_J2000_DEG = 280.46061837
GMST_DEG_PER_DAY = 360.98564736629
GMST_T2_COEFF = 0.000387933
GMST_T3_DIVISOR = 38710000.0

# A geosynchronous orbit is 1.00273790935 revolutions per sidereal day. The
# band below is deliberately wide: it is a sanity gate on "is a longitude a
# meaningful thing to plot for this object", not an orbit classifier. An
# object outside it is charted on mean motion instead, because a mean
# longitude computed for, say, a decaying LEO object is a number with no
# physical meaning that a reader would nonetheless read as a position.
GEO_MEAN_MOTION = 1.0027379
GEO_MEAN_MOTION_MIN = 0.9
GEO_MEAN_MOTION_MAX = 1.1

# Regime strings that describe a geosynchronous-family orbit. Compared
# case-insensitively against the catalogue's free-text regime field.
GEO_REGIMES = frozenset({"GEO", "GSO", "IGSO"})

METRIC_MEAN_LONGITUDE = "mean_longitude"
METRIC_MEAN_MOTION = "mean_motion"


def parse_epoch(value: object) -> dt.datetime | None:
    """Parse a UDL epoch string into an aware UTC datetime.

    UDL epochs arrive as ISO-8601 with a trailing Z and, per CONTEXT-001,
    sometimes with microseconds. `fromisoformat` handles both from Python
    3.11 onwards once the Z is translated. Anything unparsable returns None
    rather than raising: one malformed epoch in a history should drop one
    point, not fail the whole chart.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def julian_date(moment: dt.datetime) -> float:
    """Julian date for an aware datetime.

    Uses UTC where the GMST formula strictly wants UT1. The two differ by
    less than 0.9 s by definition, which is under 0.004 degrees of Earth
    rotation - four orders of magnitude below the width of a GEO
    station-keeping box, and irrelevant at this chart's scale.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.timestamp() / SECONDS_PER_DAY + JULIAN_DATE_AT_UNIX_EPOCH


def gmst_degrees(moment: dt.datetime) -> float:
    """Greenwich Mean Sidereal Time in degrees, 0 <= result < 360."""
    julian = julian_date(moment)
    days_since_j2000 = julian - J2000_JULIAN_DATE
    centuries = days_since_j2000 / JULIAN_CENTURY_DAYS
    degrees = (
        GMST_AT_J2000_DEG
        + GMST_DEG_PER_DAY * days_since_j2000
        + GMST_T2_COEFF * centuries**2
        - centuries**3 / GMST_T3_DIVISOR
    )
    return degrees % 360.0


def wrap_longitude(degrees: float) -> float:
    """Fold any angle into the -180 (inclusive) to +180 (exclusive) range."""
    return (degrees + 180.0) % 360.0 - 180.0


def mean_longitude_degrees(
    *,
    raan: float | None,
    arg_of_perigee: float | None,
    mean_anomaly: float | None,
    epoch: dt.datetime | None,
) -> float | None:
    """Approximate sub-satellite longitude for a near-geosynchronous object.

    Returns None when any input is missing, so a partial element set drops a
    point instead of inventing one. East is positive, matching the convention
    the JCO reference material uses.
    """
    if epoch is None or raan is None:
        return None
    if arg_of_perigee is None or mean_anomaly is None:
        return None
    return wrap_longitude(raan + arg_of_perigee + mean_anomaly - gmst_degrees(epoch))


def is_geo_regime(regime: str | None) -> bool:
    return bool(regime) and str(regime).strip().upper() in GEO_REGIMES


def metric_for(regime: str | None, mean_motion: float | None) -> str:
    """Choose the metric this object should be charted on.

    Mean longitude only for an object that is both catalogued as
    geosynchronous and observed to be moving like one. A catalogue regime on
    its own is not enough: a decayed or manoeuvring object still carries the
    regime it was launched into, and a mean longitude derived from a
    non-synchronous orbit is a meaningless number that a reader would take
    for a position.
    """
    if not is_geo_regime(regime):
        return METRIC_MEAN_MOTION
    if mean_motion is None:
        return METRIC_MEAN_LONGITUDE
    if GEO_MEAN_MOTION_MIN <= mean_motion <= GEO_MEAN_MOTION_MAX:
        return METRIC_MEAN_LONGITUDE
    return METRIC_MEAN_MOTION


def drift_rate_degrees_per_day(
    points: list[tuple[dt.datetime, float]],
) -> float | None:
    """East-west drift across a longitude series, in degrees per day.

    Uses the unwrapped first-to-last difference so a series that crosses the
    +/-180 seam reports a real rate rather than a 360-degree jump. Returns
    None for fewer than two points or a zero time span.
    """
    if len(points) < 2:
        return None
    first_epoch, first_value = points[0]
    last_epoch, last_value = points[-1]
    span_days = (last_epoch - first_epoch).total_seconds() / SECONDS_PER_DAY
    if math.isclose(span_days, 0.0):
        return None
    return wrap_longitude(last_value - first_value) / span_days
