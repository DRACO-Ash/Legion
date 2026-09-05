"""Tests for the orbital derivations behind the family movement charts.

Every value here is pinned to a published constant or to a physical
invariant, never to a number this code produced. A chart that silently
mis-derives longitude would look entirely plausible, so the checks that
matter are the ones an error cannot survive: an independent form of the same
GMST expression, and the requirement that a geostationary object holds its
longitude across a day.
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.orbits import (
    METRIC_MEAN_LONGITUDE,
    METRIC_MEAN_MOTION,
    drift_rate_degrees_per_day,
    gmst_degrees,
    julian_date,
    mean_longitude_degrees,
    metric_for,
    parse_epoch,
    wrap_longitude,
)

J2000 = dt.datetime(2000, 1, 1, 12, tzinfo=dt.UTC)


def _gmst_from_seconds_form(moment: dt.datetime) -> float:
    """IAU 1982 GMST in its seconds-of-time form (Vallado eq. 3-47).

    An independent expression of the same standard: same constants, arranged
    differently. If the module's degrees-and-centuries form has a transcribed
    coefficient or a units slip, these two disagree.
    """
    julian = moment.timestamp() / 86400.0 + 2440587.5
    centuries = (julian - 2451545.0) / 36525.0
    seconds = (
        67310.54841
        + (876600 * 3600 + 8640184.812866) * centuries
        + 0.093104 * centuries**2
        - 6.2e-6 * centuries**3
    )
    return (seconds % 86400.0) / 240.0


def test_julian_date_at_j2000_is_the_published_constant() -> None:
    assert julian_date(J2000) == pytest.approx(2451545.0)


def test_julian_date_at_the_unix_epoch_is_the_published_constant() -> None:
    assert julian_date(dt.datetime(1970, 1, 1, tzinfo=dt.UTC)) == pytest.approx(
        2440587.5
    )


def test_a_naive_datetime_is_read_as_utc() -> None:
    """UDL epochs are UTC; one arriving without a marker is not a different time."""
    assert julian_date(dt.datetime(2000, 1, 1, 12)) == pytest.approx(  # noqa: DTZ001
        julian_date(J2000)
    )


def test_gmst_at_j2000_is_the_published_constant() -> None:
    assert gmst_degrees(J2000) == pytest.approx(280.46061837, abs=1e-6)


@pytest.mark.parametrize(
    "moment",
    [
        dt.datetime(2026, 9, 5, tzinfo=dt.UTC),
        dt.datetime(2026, 3, 1, 7, 33, 12, tzinfo=dt.UTC),
        dt.datetime(1999, 6, 30, 23, 59, 59, tzinfo=dt.UTC),
        dt.datetime(2035, 12, 25, 18, tzinfo=dt.UTC),
    ],
)
def test_gmst_matches_an_independent_form_of_the_same_standard(moment) -> None:
    assert gmst_degrees(moment) == pytest.approx(
        _gmst_from_seconds_form(moment), abs=1e-6
    )


def test_gmst_is_always_a_bearing() -> None:
    for day in range(0, 400, 37):
        moment = dt.datetime(2026, 1, 1, tzinfo=dt.UTC) + dt.timedelta(days=day)
        assert 0.0 <= gmst_degrees(moment) < 360.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(190.0, -170.0), (-190.0, 170.0), (180.0, -180.0), (0.0, 0.0), (540.0, -180.0)],
)
def test_wrap_longitude_folds_into_one_turn(raw, expected) -> None:
    assert wrap_longitude(raw) == pytest.approx(expected)


def test_a_geostationary_object_holds_its_longitude_across_a_day() -> None:
    """The physical invariant the whole derivation rests on.

    Advance the mean anomaly by exactly one geosynchronous revolution over one
    solar day and the derived longitude must not move: the satellite has gone
    round once while the Earth turned once beneath it. This fails if the GMST
    rate and the mean-motion convention disagree even slightly.
    """
    start = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
    first = mean_longitude_degrees(
        raan=80.0, arg_of_perigee=120.0, mean_anomaly=200.0, epoch=start
    )
    advanced = (200.0 + 360.0 * 1.0027379) % 360.0
    second = mean_longitude_degrees(
        raan=80.0,
        arg_of_perigee=120.0,
        mean_anomaly=advanced,
        epoch=start + dt.timedelta(days=1),
    )
    assert first is not None and second is not None
    assert wrap_longitude(second - first) == pytest.approx(0.0, abs=0.01)


def test_longitude_advances_with_the_element_angles() -> None:
    """Ten degrees more mean anomaly at one epoch is ten degrees further east."""
    moment = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
    base = mean_longitude_degrees(
        raan=80.0, arg_of_perigee=120.0, mean_anomaly=200.0, epoch=moment
    )
    shifted = mean_longitude_degrees(
        raan=80.0, arg_of_perigee=120.0, mean_anomaly=210.0, epoch=moment
    )
    assert base is not None and shifted is not None
    assert wrap_longitude(shifted - base) == pytest.approx(10.0)


def test_longitude_is_always_inside_one_turn() -> None:
    moment = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
    for anomaly in range(0, 360, 17):
        value = mean_longitude_degrees(
            raan=350.0, arg_of_perigee=330.0, mean_anomaly=float(anomaly), epoch=moment
        )
        assert value is not None
        assert -180.0 <= value < 180.0


EPOCH = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("raan", "arg_of_perigee", "mean_anomaly", "epoch"),
    [
        (None, 120.0, 200.0, EPOCH),
        (80.0, None, 200.0, EPOCH),
        (80.0, 120.0, None, EPOCH),
        (80.0, 120.0, 200.0, None),
    ],
)
def test_a_partial_element_set_yields_no_longitude(
    raan, arg_of_perigee, mean_anomaly, epoch
) -> None:
    """A dropped point beats an invented one."""
    assert (
        mean_longitude_degrees(
            raan=raan,
            arg_of_perigee=arg_of_perigee,
            mean_anomaly=mean_anomaly,
            epoch=epoch,
        )
        is None
    )


@pytest.mark.parametrize(
    ("raw", "expected_iso"),
    [
        ("2026-08-01T12:00:00Z", "2026-08-01T12:00:00+00:00"),
        ("2026-08-01T12:00:00.123456Z", "2026-08-01T12:00:00.123456+00:00"),
        ("2026-08-01T13:00:00+01:00", "2026-08-01T12:00:00+00:00"),
        ("2026-08-01T12:00:00", "2026-08-01T12:00:00+00:00"),
    ],
)
def test_parse_epoch_normalises_to_utc(raw, expected_iso) -> None:
    parsed = parse_epoch(raw)
    assert parsed is not None
    assert parsed.isoformat() == expected_iso


@pytest.mark.parametrize("raw", ["", "   ", "not-a-date", None, 1754049600, {}])
def test_parse_epoch_returns_none_rather_than_raising(raw) -> None:
    assert parse_epoch(raw) is None


@pytest.mark.parametrize(
    ("regime", "mean_motion", "expected"),
    [
        ("GEO", 1.0027379, METRIC_MEAN_LONGITUDE),
        ("geo", None, METRIC_MEAN_LONGITUDE),
        ("IGSO", 1.0, METRIC_MEAN_LONGITUDE),
        ("GEO", 15.2, METRIC_MEAN_MOTION),
        ("LEO", 15.2, METRIC_MEAN_MOTION),
        ("HEO", 2.1, METRIC_MEAN_MOTION),
        (None, None, METRIC_MEAN_MOTION),
    ],
)
def test_metric_choice_follows_the_orbit_not_just_the_label(
    regime, mean_motion, expected
) -> None:
    """A decayed GEO object still carries the GEO label; its longitude is
    meaningless, so it is charted on mean motion instead."""
    assert metric_for(regime, mean_motion) == expected


def test_drift_rate_is_degrees_per_day() -> None:
    start = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
    points = [(start, 100.0), (start + dt.timedelta(days=10), 105.0)]
    assert drift_rate_degrees_per_day(points) == pytest.approx(0.5)


def test_drift_rate_survives_the_antimeridian() -> None:
    """A track crossing +/-180 drifts one degree a day, not 359."""
    start = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
    points = [(start, 179.0), (start + dt.timedelta(days=2), -179.0)]
    assert drift_rate_degrees_per_day(points) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "points",
    [
        [],
        [(dt.datetime(2026, 6, 1, tzinfo=dt.UTC), 100.0)],
        [
            (dt.datetime(2026, 6, 1, tzinfo=dt.UTC), 100.0),
            (dt.datetime(2026, 6, 1, tzinfo=dt.UTC), 101.0),
        ],
    ],
)
def test_drift_rate_needs_two_points_and_a_time_span(points) -> None:
    assert drift_rate_degrees_per_day(points) is None
