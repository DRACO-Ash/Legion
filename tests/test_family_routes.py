"""Tests for GET /api/udl/family-elements.

The route is the seam where the catalogue (which satellites are in this
family) meets UDL (where they are). These pin the contract the UI draws
against, and the gating that keeps a UDL-costing endpoint behind the team
token.
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


def test_the_route_is_behind_the_team_token(family_client) -> None:
    """It costs real UDL calls, so it is gated like every other UDL route."""
    assert family_client.get(PATH, params={"family_id": FAMILY_ID}).status_code == 401


def test_a_family_returns_one_series_per_member(family_client, auth_headers) -> None:
    response = family_client.get(
        PATH, params={"family_id": FAMILY_ID}, headers=auth_headers
    )
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


def test_only_the_named_family_is_returned(family_client, auth_headers) -> None:
    body = family_client.get(
        PATH, params={"family_id": FAMILY_ID}, headers=auth_headers
    ).json()
    names = {s["catalogue_name"] for chart in body["charts"] for s in chart["series"]}
    assert "SY-12 01" not in names


def test_an_unknown_family_is_a_404(family_client, auth_headers) -> None:
    response = family_client.get(
        PATH, params={"family_id": "no-such-family"}, headers=auth_headers
    )
    assert response.status_code == 404


def test_the_window_is_clamped_rather_than_rejected(
    family_client, family_udl, auth_headers
) -> None:
    response = family_client.get(
        PATH,
        params={"family_id": FAMILY_ID, "window_days": 9999},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["window_days"] == 180


def test_repeat_requests_reuse_the_cache_rather_than_udl(
    family_client, family_udl, auth_headers
) -> None:
    params = {"family_id": FAMILY_ID}
    family_client.get(PATH, params=params, headers=auth_headers)
    after_first = len(family_udl.calls)
    family_client.get(PATH, params=params, headers=auth_headers)
    assert len(family_udl.calls) == after_first


def test_an_unconfigured_udl_is_a_503(tmp_path, monkeypatch, auth_headers) -> None:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    app = build_app(
        settings=make_settings(),
        udl_client=FakeUDLClient(configured=False),
        systems_store=TrackedSystemsStore(seed_records=FAMILY_MEMBERS),
    )
    with TestClient(app) as client:
        response = client.get(
            PATH, params={"family_id": FAMILY_ID}, headers=auth_headers
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "UDL is not configured"


def test_a_total_udl_outage_is_a_502(tmp_path, monkeypatch, auth_headers) -> None:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    app = build_app(
        settings=make_settings(),
        udl_client=FakeUDLClient(raise_error=UDLError("down", status_code=503)),
        systems_store=TrackedSystemsStore(seed_records=FAMILY_MEMBERS),
    )
    with TestClient(app) as client:
        response = client.get(
            PATH, params={"family_id": FAMILY_ID}, headers=auth_headers
        )
    assert response.status_code == 502


def test_a_rank_outside_the_band_is_named_under_the_chart(
    tmp_path, monkeypatch, auth_headers
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
        body = client.get(
            PATH, params={"family_id": FAMILY_ID}, headers=auth_headers
        ).json()
    charted = [s["catalogue_name"] for chart in body["charts"] for s in chart["series"]]
    assert charted == ["TJS-3"]
    assert body["skipped"] == [
        {"catalogue_name": "TJS-10", "reason": "JCO HRR rank 5, outside the 0-3 band"}
    ]


def test_a_zero_window_reaches_udl_as_a_request_for_everything(
    family_client, family_udl, auth_headers
) -> None:
    response = family_client.get(
        PATH, params={"family_id": FAMILY_ID, "window_days": 0}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["window_days"] == 0
    history_calls = [c for c in family_udl.calls if c["op"] == "get_elset_history"]
    assert history_calls and all(call["since"] is None for call in history_calls)


def test_the_series_carries_the_rank_that_let_it_through(
    family_client, auth_headers
) -> None:
    body = family_client.get(
        PATH, params={"family_id": FAMILY_ID}, headers=auth_headers
    ).json()
    ranks = {s["catalogue_name"]: s["hrr_rank"] for s in body["charts"][0]["series"]}
    assert ranks == {"TJS-3": TRUSTED_RANK, "TJS-10": TRUSTED_RANK}
