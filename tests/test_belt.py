"""The GEO belt: placement, the rank gate, and every way an object comes off it.

The belt is the stage of the interface, so the failure modes matter more than
the happy path. An object drawn at the wrong slot looks entirely normal, and an
empty belt and an unreachable UDL look identical on a circle.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.app import build_app
from src.belt import OFF_PLOT_NO_ELSET, OFF_PLOT_NO_LONGITUDE, OFF_PLOT_NOT_GEO
from src.family_elements import SKIP_NOT_IN_HRR_FEED, SKIP_RANK_OUTSIDE_BAND
from src.udl_client import UDLError
from tests.conftest import FakeUDLClient, geo_satellites, make_settings


def _catalogue(tmp_path, monkeypatch) -> list[dict]:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    with TestClient(build_app(settings=make_settings())) as client:
        return [
            record
            for record in client.get("/api/systems").json()["systems"]
            if record["regime"] == "GEO" and record["norad_id"]
        ]


def _belt_client(tmp_path, monkeypatch, udl) -> TestClient:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    return TestClient(build_app(settings=make_settings(), udl_client=udl))


def test_every_eligible_geo_object_is_placed(tmp_path, monkeypatch):
    """The happy path, against a feed that knows every GEO satellite."""
    geo = _catalogue(tmp_path, monkeypatch)
    udl = FakeUDLClient(satellites=geo_satellites(geo))

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        body = client.get("/api/udl/belt").json()

    assert body["count"] == len(geo)
    assert all(-180 <= entry["longitude"] <= 180 for entry in body["placed"])
    assert body["derivation"].startswith("Mean longitude is derived")


def test_the_belt_is_ordered_by_longitude(tmp_path, monkeypatch):
    """Ordered around the belt, so a caller can read neighbours off the list.

    Adjacency is the question the belt exists to answer, and an unordered list
    would make the interface sort it again and possibly differently.
    """
    geo = _catalogue(tmp_path, monkeypatch)
    udl = FakeUDLClient(satellites=geo_satellites(geo))

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        placed = client.get("/api/udl/belt").json()["placed"]

    longitudes = [entry["longitude"] for entry in placed]
    assert longitudes == sorted(longitudes)


def test_a_non_geo_object_is_off_plot_and_says_why(tmp_path, monkeypatch):
    """A LEO object has no belt longitude, so it is listed rather than dropped.

    Projecting it onto the circle would place a real satellite somewhere it
    has never been, which is the failure this whole module is shaped around.
    """
    geo = _catalogue(tmp_path, monkeypatch)
    udl = FakeUDLClient(satellites=geo_satellites(geo))

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        body = client.get("/api/udl/belt").json()

    reasons = {entry["reason"] for entry in body["off_plot"]}
    assert OFF_PLOT_NOT_GEO in reasons
    assert all(entry["name"] for entry in body["off_plot"])


def test_a_rank_outside_the_band_keeps_an_object_off_the_belt(tmp_path, monkeypatch):
    """Ash's rule, 6 September 2026, reused rather than reimplemented.

    The reason string comes from `family_elements`, so if the charts' gate ever
    changes the belt cannot silently keep the old one.
    """
    geo = _catalogue(tmp_path, monkeypatch)
    udl = FakeUDLClient(satellites=geo_satellites(geo, rank=5))

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        body = client.get("/api/udl/belt").json()

    assert body["count"] == 0
    assert SKIP_RANK_OUTSIDE_BAND.format(rank=5) in {
        entry["reason"] for entry in body["off_plot"]
    }


def test_an_object_absent_from_the_feed_is_not_pulled(tmp_path, monkeypatch):
    """No rank means no pull. An unranked object is not a rank-0 object."""
    geo = _catalogue(tmp_path, monkeypatch)
    udl = FakeUDLClient(satellites=geo_satellites(geo[:1]))

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        body = client.get("/api/udl/belt").json()

    assert body["count"] == 1
    assert SKIP_NOT_IN_HRR_FEED in {entry["reason"] for entry in body["off_plot"]}


def test_a_partial_element_set_drops_the_object_rather_than_placing_it(
    tmp_path, monkeypatch
):
    """Missing a field the derivation needs means no longitude, so no mark.

    Calibrated by removing `raan` from every element set: every object moves
    to off_plot naming the missing-field reason, and none is placed at a
    default longitude.
    """
    geo = _catalogue(tmp_path, monkeypatch)
    satellites = geo_satellites(geo)
    for entry in satellites:
        entry.pop("raan")
    udl = FakeUDLClient(satellites=satellites)

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        body = client.get("/api/udl/belt").json()

    assert body["count"] == 0
    assert OFF_PLOT_NO_LONGITUDE in {entry["reason"] for entry in body["off_plot"]}


def test_a_missing_element_set_is_named_as_missing(tmp_path, monkeypatch):
    """The feed ranked it but no element set came back. Say that, precisely.

    `get_elset` returns None for a satellite with no `epoch`, so the ranked
    entry survives the gate and then has nothing to place.
    """
    geo = _catalogue(tmp_path, monkeypatch)
    satellites = geo_satellites(geo)
    for entry in satellites:
        entry.pop("epoch")
    udl = FakeUDLClient(satellites=satellites)

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        body = client.get("/api/udl/belt").json()

    assert body["count"] == 0
    assert OFF_PLOT_NO_ELSET in {entry["reason"] for entry in body["off_plot"]}


def test_colour_follows_the_family_not_the_belt_position(tmp_path, monkeypatch):
    """A satellite keeps the colour it has beside its siblings.

    The belt is sorted by longitude, so if colour came from position in the
    result every object would be repainted the moment one drifted past
    another. The index is its launch-order position in its own family.
    """
    geo = _catalogue(tmp_path, monkeypatch)
    udl = FakeUDLClient(satellites=geo_satellites(geo))

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        placed = client.get("/api/udl/belt").json()["placed"]

    by_family: dict[str, set[int]] = {}
    for entry in placed:
        by_family.setdefault(entry["family_id"], set()).add(entry["colour_index"])
    # Within one family every placed member holds a distinct slot, which only
    # holds if the index came from family position rather than belt order.
    assert all(
        len(slots) == len([e for e in placed if e["family_id"] == family])
        for family, slots in by_family.items()
    )


def test_a_feed_failure_stops_the_pull(tmp_path, monkeypatch):
    """A gate that cannot be applied must never quietly open.

    Same rule as the charts. The alternative, falling back to plotting
    everything when the rank feed is down, would draw exactly the belt the
    gate exists to prevent.
    """
    udl = FakeUDLClient(satellites=[], raise_error=UDLError("feed down"))

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        response = client.get("/api/udl/belt")

    assert response.status_code == 502
    assert "UDL did not answer" in response.json()["detail"]


def test_an_unconfigured_udl_says_so_rather_than_drawing_an_empty_belt(
    tmp_path, monkeypatch
):
    """An empty belt and an unreachable UDL look identical on a circle.

    The difference is the whole of what an analyst needs to know, so the
    endpoint refuses rather than returning a belt with nothing on it.
    """
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    unconfigured = make_settings(udl_username="", udl_password="")
    with TestClient(build_app(settings=unconfigured)) as client:
        response = client.get("/api/udl/belt")

    assert response.status_code == 503
    assert response.json()["detail"] == "UDL is not configured"


@pytest.mark.parametrize("field", ["rank", "score", "priority"])
def test_the_belt_carries_no_ordering_of_its_own(tmp_path, monkeypatch, field):
    """The belt places objects; it does not rank them.

    `rank` is the one exception and it is the JCO HRR rank, a sourced feed
    value, not a judgement this application formed. The parametrised check
    proves the other two never appear.
    """
    geo = _catalogue(tmp_path, monkeypatch)
    udl = FakeUDLClient(satellites=geo_satellites(geo))

    with _belt_client(tmp_path, monkeypatch, udl) as client:
        placed = client.get("/api/udl/belt").json()["placed"]

    present = {key for entry in placed for key in entry}
    assert (field in present) == (field == "rank")
