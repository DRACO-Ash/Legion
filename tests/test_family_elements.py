"""Tests for assembling a family's element sets into chart-ready series.

The behaviours pinned here are the ones a reader of the chart depends on
without knowing it: that a satellite keeps its colour, that one satellite's
outage costs one line rather than the chart, that a GEO and a LEO object never
share an axis, and that the inferred history endpoint being unavailable
degrades to a single point instead of an error.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from src.family_elements import (
    MAX_SERIES,
    NOTE_LATEST_ONLY,
    NOTE_NO_ELEMENT_SET,
    NOTE_NO_USABLE_POINTS,
    NOTE_UDL_FAILED,
    SKIP_NO_NORAD_ID,
    SOURCE_HISTORY,
    SOURCE_LATEST,
    SOURCE_MIXED,
    build_family_charts,
    clamp_window_days,
    order_members,
)
from src.orbits import METRIC_MEAN_LONGITUDE, METRIC_MEAN_MOTION
from src.udl_client import UDLError

from .conftest import FakeUDLClient, make_elset, make_seed_record

NOW = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
FAMILY_ID = "chn-sj"
FAMILY_TITLE = "Shijian (SJ) Programme"


def _member(**overrides) -> dict:
    base = {"family_id": FAMILY_ID, "family_title": FAMILY_TITLE, "archived": False}
    base.update(overrides)
    return make_seed_record(**base)


# Degrees the Earth turns past one full rotation in a solar day. A satellite
# whose mean anomaly advances by exactly this much per day holds its longitude;
# anything more is eastward drift.
EARTH_DAILY_EXCESS_DEG = 360.98564736629 % 360.0


def _history(
    sat_no: str, count: int = 4, drift_per_day: float = 1.0, **elset_overrides
) -> list[dict]:
    """A run of element sets, one a day, ending the day before NOW.

    The mean anomaly advances by the Earth's daily excess plus the requested
    drift, so the derived longitude moves east at exactly `drift_per_day`.
    """
    return [
        make_elset(
            satNo=sat_no,
            epoch=(NOW - dt.timedelta(days=count - offset)).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            meanAnomaly=(200.0 + offset * (EARTH_DAILY_EXCESS_DEG + drift_per_day))
            % 360.0,
            **elset_overrides,
        )
        for offset in range(count)
    ]


def _build(client, members, **overrides):
    kwargs = {
        "client": client,
        "cache": None,
        "family_id": FAMILY_ID,
        "family_title": FAMILY_TITLE,
        "members": members,
        "window_days": 30,
        "now": NOW,
    }
    kwargs.update(overrides)
    return asyncio.run(build_family_charts(**kwargs))


GEO_MEMBERS = [
    _member(catalogue_name="SJ-17", norad_id="41838", regime="GEO", launch_year=2016),
    _member(catalogue_name="SJ-21", norad_id="49330", regime="GEO", launch_year=2021),
    _member(catalogue_name="SJ-23", norad_id="55131", regime="GEO", launch_year=2023),
]


def _geo_client(**overrides) -> FakeUDLClient:
    return FakeUDLClient(
        elset_history={
            "41838": _history("41838"),
            "49330": _history("49330"),
            "55131": _history("55131"),
        },
        **overrides,
    )


def test_a_geo_family_produces_one_longitude_chart() -> None:
    response = _build(_geo_client(), GEO_MEMBERS)
    assert [chart.metric for chart in response.charts] == [METRIC_MEAN_LONGITUDE]
    assert response.source == SOURCE_HISTORY
    chart = response.charts[0]
    assert [s.catalogue_name for s in chart.series] == ["SJ-17", "SJ-21", "SJ-23"]
    assert all(len(s.points) == 4 for s in chart.series)


def test_every_point_carries_an_epoch_and_a_value() -> None:
    chart = _build(_geo_client(), GEO_MEMBERS).charts[0]
    for point in chart.series[0].points:
        assert point.epoch.endswith("+00:00")
        assert -180.0 <= point.value < 180.0


def test_points_are_ordered_oldest_first_whatever_udl_returned() -> None:
    shuffled = list(reversed(_history("41838")))
    client = FakeUDLClient(elset_history={"41838": shuffled})
    series = _build(client, GEO_MEMBERS[:1]).charts[0].series[0]
    epochs = [point.epoch for point in series.points]
    assert epochs == sorted(epochs)


def test_colour_follows_the_entity_not_the_result_order() -> None:
    """Filtering a member out must not repaint the survivors."""
    full = _build(_geo_client(), GEO_MEMBERS).charts[0].series
    colours = {s.catalogue_name: s.colour_index for s in full}

    without_the_first = _build(_geo_client(), GEO_MEMBERS[1:]).charts[0].series
    # SJ-21 and SJ-23 keep their launch-order positions; only SJ-17 leaves.
    assert [s.colour_index for s in without_the_first] == [0, 1]
    assert colours == {"SJ-17": 0, "SJ-21": 1, "SJ-23": 2}


def test_members_are_ordered_by_launch_year() -> None:
    ordered = order_members(list(reversed(GEO_MEMBERS)))
    assert [m["catalogue_name"] for m in ordered] == ["SJ-17", "SJ-21", "SJ-23"]


def test_a_mixed_family_gets_one_chart_per_metric_never_two_axes() -> None:
    members = [
        *GEO_MEMBERS[:1],
        _member(
            catalogue_name="SHIYAN 24C 01",
            norad_id="58650",
            regime="LEO",
            launch_year=2023,
        ),
    ]
    client = FakeUDLClient(
        elset_history={
            "41838": _history("41838"),
            "58650": _history("58650", meanMotion=15.2),
        }
    )
    response = _build(client, members)
    assert [chart.metric for chart in response.charts] == [
        METRIC_MEAN_LONGITUDE,
        METRIC_MEAN_MOTION,
    ]
    assert response.charts[1].series[0].points[0].value == pytest.approx(15.2)


def test_a_geo_object_no_longer_in_a_geo_orbit_moves_to_the_mean_motion_chart() -> None:
    """A decayed object keeps its catalogue regime; its longitude does not
    keep its meaning."""
    client = FakeUDLClient(elset_history={"41838": _history("41838", meanMotion=15.9)})
    response = _build(client, GEO_MEMBERS[:1])
    assert [chart.metric for chart in response.charts] == [METRIC_MEAN_MOTION]


def test_a_longitude_series_reports_its_drift_rate() -> None:
    client = FakeUDLClient(
        elset_history={"41838": _history("41838", drift_per_day=1.0)}
    )
    series = _build(client, GEO_MEMBERS[:1]).charts[0].series[0]
    assert series.drift_deg_per_day == pytest.approx(1.0, abs=0.01)


def test_a_satellite_holding_station_reports_no_meaningful_drift() -> None:
    client = FakeUDLClient(
        elset_history={"41838": _history("41838", drift_per_day=0.0)}
    )
    series = _build(client, GEO_MEMBERS[:1]).charts[0].series[0]
    assert series.drift_deg_per_day == pytest.approx(0.0, abs=0.01)


def test_a_mean_motion_series_reports_no_drift_rate() -> None:
    client = FakeUDLClient(elset_history={"58650": _history("58650", meanMotion=15.2)})
    member = _member(catalogue_name="SHIYAN", norad_id="58650", regime="LEO")
    series = _build(client, [member]).charts[0].series[0]
    assert series.drift_deg_per_day is None
    assert series.latest_value == pytest.approx(15.2)


def test_history_being_unavailable_degrades_to_the_latest_element_set() -> None:
    """The /udl/elset/history path is an inference. If it is not there, the
    chart still draws - one point per satellite instead of a track."""
    client = FakeUDLClient(
        history_supported=False,
        satellites=[make_elset(satNo="41838")],
    )
    response = _build(client, GEO_MEMBERS[:1])
    series = response.charts[0].series[0]
    assert response.source == SOURCE_LATEST
    assert len(series.points) == 1
    assert series.note == NOTE_LATEST_ONLY


def test_a_satellite_udl_has_nothing_for_keeps_its_place_with_a_note() -> None:
    client = FakeUDLClient(elset_history={"41838": _history("41838")})
    response = _build(client, GEO_MEMBERS)
    notes = {s.catalogue_name: s.note for s in response.charts[0].series}
    assert notes["SJ-17"] is None
    assert notes["SJ-21"] == NOTE_NO_ELEMENT_SET
    assert notes["SJ-23"] == NOTE_NO_ELEMENT_SET


def test_element_sets_without_the_needed_fields_are_reported_not_plotted() -> None:
    stripped = [
        make_elset(
            satNo="41838",
            raan=None,
            epoch=(NOW - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        )
    ]
    client = FakeUDLClient(elset_history={"41838": stripped})
    series = _build(client, GEO_MEMBERS[:1]).charts[0].series[0]
    assert series.points == []
    assert series.note == NOTE_NO_USABLE_POINTS


def test_a_non_numeric_field_drops_the_point_rather_than_the_chart() -> None:
    junk = _history("58650", count=1, meanMotion="unavailable")
    client = FakeUDLClient(elset_history={"58650": junk})
    member = _member(catalogue_name="SHIYAN", norad_id="58650", regime="LEO")
    series = _build(client, [member]).charts[0].series[0]
    assert series.points == []
    assert series.note == NOTE_NO_USABLE_POINTS


def test_a_family_split_across_both_udl_paths_reports_a_mixed_source() -> None:
    """One satellite with history, one without, is not a uniform answer and
    the response says so rather than implying every track is equally deep."""

    class HistoryForOneOnly(FakeUDLClient):
        async def get_elset_history(self, sat_no, *, since):
            if sat_no == "49330":
                return None
            return await super().get_elset_history(sat_no, since=since)

    client = HistoryForOneOnly(
        elset_history={"41838": _history("41838")},
        satellites=[make_elset(satNo="49330")],
    )
    response = _build(client, GEO_MEMBERS[:2])
    assert response.source == SOURCE_MIXED


def test_one_satellite_failing_costs_one_line_not_the_chart() -> None:
    class OneBadSatellite(FakeUDLClient):
        async def get_elset_history(self, sat_no, *, since):
            if sat_no == "49330":
                raise UDLError("upstream said no", status_code=500)
            return await super().get_elset_history(sat_no, since=since)

    client = OneBadSatellite(
        elset_history={
            "41838": _history("41838"),
            "55131": _history("55131"),
        }
    )
    series = {s.catalogue_name: s for s in _build(client, GEO_MEMBERS).charts[0].series}
    assert series["SJ-21"].note == NOTE_UDL_FAILED
    assert series["SJ-17"].points


def test_every_satellite_failing_is_an_outage_and_raises() -> None:
    client = FakeUDLClient(raise_error=UDLError("upstream down", status_code=502))
    with pytest.raises(UDLError):
        _build(client, GEO_MEMBERS)


def test_a_member_without_a_norad_id_is_skipped_with_a_reason() -> None:
    members = [*GEO_MEMBERS[:1], _member(catalogue_name="Object E", norad_id=None)]
    response = _build(_geo_client(), members)
    assert [s.catalogue_name for s in response.skipped] == ["Object E"]
    assert response.skipped[0].reason == SKIP_NO_NORAD_ID


def test_a_family_past_the_palette_limit_skips_the_tail_rather_than_reusing_a_colour() -> (
    None
):
    members = [
        _member(
            catalogue_name=f"SAT-{index:02d}",
            norad_id=str(50000 + index),
            launch_year=2000 + index,
            regime="LEO",
        )
        for index in range(MAX_SERIES + 2)
    ]
    response = _build(FakeUDLClient(), members)
    assert len(response.skipped) == 2
    charted = sum(len(chart.series) for chart in response.charts)
    assert charted == MAX_SERIES


def test_the_cache_spares_udl_a_second_identical_lookup() -> None:
    class CountingCache:
        def __init__(self):
            self.store: dict = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, value):
            self.store[key] = value

    cache = CountingCache()
    client = _geo_client()
    _build(client, GEO_MEMBERS, cache=cache)
    calls_after_first = len(client.calls)
    _build(client, GEO_MEMBERS, cache=cache)
    assert len(client.calls) == calls_after_first
    assert len(cache.store) == len(GEO_MEMBERS)


def test_the_window_bounds_what_is_asked_of_udl() -> None:
    client = _geo_client()
    _build(client, GEO_MEMBERS[:1], window_days=7)
    since = client.calls[0]["since"]
    assert since == NOW - dt.timedelta(days=7)


@pytest.mark.parametrize(
    ("requested", "expected"), [(None, 30), (0, 1), (-5, 1), (5, 5), (9999, 180)]
)
def test_the_window_is_clamped_to_a_sane_range(requested, expected) -> None:
    assert clamp_window_days(requested) == expected


def test_an_empty_family_produces_no_charts_rather_than_an_error() -> None:
    response = _build(_geo_client(), [])
    assert response.charts == []
    assert response.skipped == []
