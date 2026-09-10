"""Tests for GET /api/udl/family-elements.

The route is the seam where the catalogue (which satellites are in this
family) meets UDL (where they are). These pin the contract the UI draws
against, for the whole family and for a single object from the table.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from src.app import build_app
from src.orbits import METRIC_MEAN_LONGITUDE
from src.store import TrackedSystemsStore
from src.udl_client import UDLError

from .conftest import FakeUDLClient, make_elset, make_seed_record, make_settings

FAMILY_ID = "chn-tjs"
PATH = "/api/udl/family-elements"
FAMILY_TITLE = "TJS Signals Collection"
NOW = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)

FAMILY_MEMBERS = [
    make_seed_record(
        family_id=FAMILY_ID,
        family_title=FAMILY_TITLE,
        catalogue_name="TJS-3",
        norad_id="43874",
        regime="GEO",
        launch_year=2018,
    ),
    make_seed_record(
        family_id=FAMILY_ID,
        family_title=FAMILY_TITLE,
        catalogue_name="TJS-10",
        norad_id="58204",
        regime="GEO",
        launch_year=2023,
    ),
    make_seed_record(
        family_id="chn-other",
        family_title="Another Family",
        catalogue_name="SY-12 01",
        norad_id="50321",
        regime="GEO",
        launch_year=2021,
    ),
]


def _recent_elset(sat_no: str, days_ago: int) -> dict:
    return make_elset(
        satNo=sat_no,
        epoch=(NOW - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )


# Ranks 0 to 3 are the band the chart pulls for; make_settings' HRR window is
# what the route asks the feed for.
TRUSTED_RANK = 1


@pytest.fixture
def family_udl() -> FakeUDLClient:
    return FakeUDLClient(
        elset_history={
            "43874": [_recent_elset("43874", 3), _recent_elset("43874", 1)],
            "58204": [_recent_elset("58204", 2)],
        },
        hrr=[
            {"commonName": "TJS-3", "satNo": "43874", "rank": TRUSTED_RANK},
            {"commonName": "TJS-10", "satNo": "58204", "rank": TRUSTED_RANK},
        ],
    )


@pytest.fixture
def family_client(family_udl, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    app = build_app(
        settings=make_settings(),
        udl_client=family_udl,
        systems_store=TrackedSystemsStore(seed_records=FAMILY_MEMBERS),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_the_route_needs_no_token(family_client) -> None:
    """It costs real UDL calls, and the strict rate limiter is what protects
    that budget. The bearer token that used to gate it was removed in 0.9.0:
    it blocked the charts this route exists to draw."""
    assert family_client.get(PATH, params={"family_id": FAMILY_ID}).status_code == 200


def test_a_family_returns_one_series_per_member(family_client) -> None:
    response = family_client.get(PATH, params={"family_id": FAMILY_ID})
    assert response.status_code == 200
    body = response.json()
    assert body["family_id"] == FAMILY_ID
    assert body["family_title"] == FAMILY_TITLE
    assert len(body["charts"]) == 1
    chart = body["charts"][0]
    assert chart["metric"] == METRIC_MEAN_LONGITUDE
    assert chart["unit"]
    assert [s["catalogue_name"] for s in chart["series"]] == ["TJS-3", "TJS-10"]
    assert len(chart["series"][0]["points"]) == 2


def test_only_the_named_family_is_returned(family_client) -> None:
    body = family_client.get(PATH, params={"family_id": FAMILY_ID}).json()
    names = {s["catalogue_name"] for chart in body["charts"] for s in chart["series"]}
    assert "SY-12 01" not in names


def test_an_unknown_family_is_a_404(family_client) -> None:
    response = family_client.get(PATH, params={"family_id": "no-such-family"})
    assert response.status_code == 404


def test_the_window_is_clamped_rather_than_rejected(family_client, family_udl) -> None:
    response = family_client.get(
        PATH,
        params={"family_id": FAMILY_ID, "window_days": 9999},
    )
    assert response.status_code == 200
    assert response.json()["window_days"] == 180


def test_repeat_requests_reuse_the_cache_rather_than_udl(
    family_client, family_udl
) -> None:
    params = {"family_id": FAMILY_ID}
    family_client.get(PATH, params=params)
    after_first = len(family_udl.calls)
    family_client.get(PATH, params=params)
    assert len(family_udl.calls) == after_first


def test_an_unconfigured_udl_is_a_503(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    app = build_app(
        settings=make_settings(),
        udl_client=FakeUDLClient(configured=False),
        systems_store=TrackedSystemsStore(seed_records=FAMILY_MEMBERS),
    )
    with TestClient(app) as client:
        response = client.get(PATH, params={"family_id": FAMILY_ID})
    assert response.status_code == 503
    assert response.json()["detail"] == "UDL is not configured"


def test_a_total_udl_outage_is_a_502(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    app = build_app(
        settings=make_settings(),
        udl_client=FakeUDLClient(raise_error=UDLError("down", status_code=503)),
        systems_store=TrackedSystemsStore(seed_records=FAMILY_MEMBERS),
    )
    with TestClient(app) as client:
        response = client.get(PATH, params={"family_id": FAMILY_ID})
    assert response.status_code == 502


def test_a_rank_outside_the_band_is_named_under_the_chart(
    tmp_path, monkeypatch
) -> None:
    """The analyst sees why an object is missing, not just that it is."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    udl = FakeUDLClient(
        elset_history={
            "43874": [_recent_elset("43874", 1)],
            "58204": [_recent_elset("58204", 1)],
        },
        hrr=[
            {"commonName": "TJS-3", "satNo": "43874", "rank": TRUSTED_RANK},
            {"commonName": "TJS-10", "satNo": "58204", "rank": 5},
        ],
    )
    app = build_app(
        settings=make_settings(),
        udl_client=udl,
        systems_store=TrackedSystemsStore(seed_records=FAMILY_MEMBERS),
    )
    with TestClient(app) as client:
        body = client.get(PATH, params={"family_id": FAMILY_ID}).json()
    charted = [s["catalogue_name"] for chart in body["charts"] for s in chart["series"]]
    assert charted == ["TJS-3"]
    assert body["skipped"] == [
        {"catalogue_name": "TJS-10", "reason": "JCO HRR rank 5, outside the 0-3 band"}
    ]


def test_a_zero_window_reaches_udl_as_a_request_for_everything(
    family_client, family_udl
) -> None:
    response = family_client.get(
        PATH, params={"family_id": FAMILY_ID, "window_days": 0}
    )
    assert response.status_code == 200
    assert response.json()["window_days"] == 0
    history_calls = [c for c in family_udl.calls if c["op"] == "get_elset_history"]
    assert history_calls and all(call["since"] is None for call in history_calls)


def test_the_series_carries_the_rank_that_let_it_through(family_client) -> None:
    body = family_client.get(PATH, params={"family_id": FAMILY_ID}).json()
    ranks = {s["catalogue_name"]: s["hrr_rank"] for s in body["charts"][0]["series"]}
    assert ranks == {"TJS-3": TRUSTED_RANK, "TJS-10": TRUSTED_RANK}


# --- GET /api/udl/object-elements -------------------------------------------
#
# Selecting one row in the catalogue plots that object. It is the same chart
# with the same rules, so these tests are mostly about proving it does not
# quietly become a second, looser implementation.

OBJECT_PATH = "/api/udl/object-elements"


def _record_id(client, catalogue_name: str) -> str:
    systems = client.get("/api/systems").json()["systems"]
    return next(s["id"] for s in systems if s["catalogue_name"] == catalogue_name)


def test_one_object_returns_only_its_own_series(family_client) -> None:
    record_id = _record_id(family_client, "TJS-3")
    body = family_client.get(OBJECT_PATH, params={"record_id": record_id}).json()
    names = [
        series["catalogue_name"]
        for chart in body["charts"]
        for series in chart["series"]
    ]
    assert names == ["TJS-3"]


def test_an_object_keeps_the_colour_it_has_in_its_family(family_client) -> None:
    """The rule is that colour follows the satellite, not its position in the
    result. TJS-10 is second by launch year in its family, so it must be the
    second colour whether it is charted beside TJS-3 or on its own."""
    family = family_client.get(PATH, params={"family_id": FAMILY_ID}).json()
    in_family = {
        series["catalogue_name"]: series["colour_index"]
        for chart in family["charts"]
        for series in chart["series"]
    }
    alone = family_client.get(
        OBJECT_PATH, params={"record_id": _record_id(family_client, "TJS-10")}
    ).json()
    solo_index = alone["charts"][0]["series"][0]["colour_index"]
    assert solo_index == in_family["TJS-10"]
    assert solo_index != in_family["TJS-3"]


def test_the_rank_gate_still_applies_to_a_single_object(tmp_path, monkeypatch) -> None:
    """Rank 4 is outside Ash's trusted band. Charting one object must not be a
    way round the gate: it comes back named in `skipped`, with no series."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    udl = FakeUDLClient(
        elset_history={"43874": [_recent_elset("43874", 1)]},
        hrr=[{"commonName": "TJS-3", "satNo": "43874", "rank": 4}],
    )
    app = build_app(
        settings=make_settings(),
        udl_client=udl,
        systems_store=TrackedSystemsStore(seed_records=FAMILY_MEMBERS),
    )
    with TestClient(app) as client:
        body = client.get(
            OBJECT_PATH, params={"record_id": _record_id(client, "TJS-3")}
        ).json()
    assert body["charts"] == []
    assert [entry["catalogue_name"] for entry in body["skipped"]] == ["TJS-3"]
    assert "rank 4" in body["skipped"][0]["reason"]


def test_only_the_selected_object_is_reported_as_skipped(
    family_client, family_udl
) -> None:
    """A sibling excluded from the family chart is not this object's business,
    and listing it under a single-object chart would read as a fault here."""
    body = family_client.get(
        OBJECT_PATH, params={"record_id": _record_id(family_client, "TJS-3")}
    ).json()
    assert body["skipped"] == []


def test_the_window_applies_to_a_single_object(family_client, family_udl) -> None:
    record_id = _record_id(family_client, "TJS-3")
    body = family_client.get(
        OBJECT_PATH, params={"record_id": record_id, "window_days": 0}
    ).json()
    assert body["window_days"] == 0


def test_an_unknown_record_is_a_404(family_client) -> None:
    response = family_client.get(OBJECT_PATH, params={"record_id": "not-a-real-id"})
    assert response.status_code == 404


def test_a_record_without_a_norad_id_says_so(family_client) -> None:
    """There is nothing to ask UDL for, and "no system with that id" would be
    a lie: the record exists, it just carries no catalogue number."""
    created = family_client.post(
        "/api/systems",
        json={
            "family_id": FAMILY_ID,
            "family_title": FAMILY_TITLE,
            "family_sub": "signals collection",
            "nation": "CN",
            "catalogue_name": "TJS-UNCATALOGUED",
            "launch_year": 2026,
            "regime": "GEO",
        },
    ).json()
    response = family_client.get(OBJECT_PATH, params={"record_id": created["id"]})
    assert response.status_code == 404
    assert "no NORAD ID" in response.json()["detail"]


def test_a_single_object_costs_one_element_set_lookup(
    family_client, family_udl
) -> None:
    """Passing the whole family in is how colour stays stable, but it must not
    mean fetching the whole family."""

    def elset_lookups():
        return [
            c for c in family_udl.calls if c["op"] in {"get_elset_history", "get_elset"}
        ]

    before = len(elset_lookups())
    family_client.get(
        OBJECT_PATH, params={"record_id": _record_id(family_client, "TJS-3")}
    )
    assert len(elset_lookups()) - before == 1
