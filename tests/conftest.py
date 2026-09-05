from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.app import build_app
from src.config import Settings
from src.orbits import parse_epoch
from src.udl_client import UDLNotConfigured


class FakeUDLClient:
    """In-process double for UDLClient. No network call ever happens in tests."""

    def __init__(
        self,
        *,
        configured: bool = True,
        satellites: list[dict] | None = None,
        raise_error: Exception | None = None,
        elset_history: dict[str, list[dict]] | None = None,
        history_supported: bool = True,
    ):
        self._configured = configured
        self._satellites = satellites if satellites is not None else []
        self._raise_error = raise_error
        # Keyed by satNo. `history_supported=False` reproduces UDL answering
        # 4xx for /udl/elset/history, which is the fallback path the charts
        # have to survive, since that endpoint is an inference.
        self._elset_history = elset_history or {}
        self._history_supported = history_supported
        self.calls: list[dict] = []

    @property
    def configured(self) -> bool:
        return self._configured

    async def aclose(self) -> None:
        return None

    def _check(self):
        if self._raise_error:
            raise self._raise_error
        if not self._configured:
            raise UDLNotConfigured("not configured")

    async def fetch_jco_hrr(self, *, window_hours: int = 24):
        self.calls.append({"op": "fetch_jco_hrr", "window_hours": window_hours})
        self._check()
        return list(self._satellites)

    async def find_by_common_name(self, common_name: str, *, window_hours: int = 24):
        self.calls.append(
            {
                "op": "find_by_common_name",
                "common_name": common_name,
                "window_hours": window_hours,
            }
        )
        self._check()
        target = common_name.strip().casefold()
        for entry in self._satellites:
            if str(entry.get("commonName", "")).strip().casefold() == target:
                return entry
        return None

    async def search_by_common_name(self, query: str, *, window_hours: int = 24):
        self.calls.append(
            {
                "op": "search_by_common_name",
                "query": query,
                "window_hours": window_hours,
            }
        )
        self._check()
        needle = query.strip().casefold()
        return [
            e
            for e in self._satellites
            if needle in str(e.get("commonName", "")).strip().casefold()
        ]

    async def get_elset_history(self, sat_no: str, *, since):
        self.calls.append({"op": "get_elset_history", "sat_no": sat_no, "since": since})
        self._check()
        if not self._history_supported:
            return None
        records = self._elset_history.get(str(sat_no), [])
        return [
            record
            for record in records
            if parse_epoch(record.get("epoch")) is None
            or parse_epoch(record.get("epoch")) >= since
        ]

    async def get_elset(self, sat_no: str):
        self.calls.append({"op": "get_elset", "sat_no": sat_no})
        self._check()
        for entry in self._satellites:
            if str(entry.get("satNo")) == str(sat_no) and "epoch" in entry:
                return entry
        return None


def make_settings(**overrides) -> Settings:
    base = {
        "port": 8080,
        "allowed_origin": "http://localhost:3000",
        "team_token": "test-token",
        "udl_base_url": "https://unifieddatalibrary.com",
        "udl_username": "user",
        "udl_password": "pass",
        "udl_timeout_seconds": 5.0,
        "udl_jco_hrr_window_hours": 24,
    }
    base.update(overrides)
    return Settings(**base)


def make_seed_record(**overrides) -> dict:
    """One canonical minimal tracked-system record for tests.

    Shared because the platform's SonarQube gate measures duplicated lines on
    new code against a 3% threshold, and a copy of this literal in a new test
    file is a duplicated block large enough to fail it on its own.
    """
    record = {
        "family_id": "test-fam",
        "family_title": "Test Family",
        "family_sub": "sub",
        "nation": "RU",
        "designator": "TEST-1",
        "catalogue_name": "TESTSAT-1",
        "launch_year": 2020,
        "launch_site": None,
        "norad_id": None,
        "regime": "LEO",
        "delta_v": None,
        "status": "unknown",
        "life": None,
        "coplanar": None,
        "notes": None,
        "flag": None,
    }
    record.update(overrides)
    return record


def make_elset(**overrides) -> dict:
    """One canonical UDL element set for tests.

    Shared for the same reason as make_seed_record: the platform measures
    duplicated lines on new code, and an eight-key literal copied into a
    second test file is a duplicated block large enough to fail the gate on
    its own. Values describe a near-geostationary object so that the default
    is charted on mean longitude.
    """
    record = {
        "satNo": "41838",
        "epoch": "2026-08-01T00:00:00.000000Z",
        "inclination": 0.06,
        "eccentricity": 0.0002,
        "raan": 80.0,
        "argOfPerigee": 120.0,
        "meanAnomaly": 200.0,
        "meanMotion": 1.0027379,
    }
    record.update(overrides)
    return record


@pytest.fixture
def fake_udl():
    return FakeUDLClient(
        satellites=[
            {
                "commonName": "COSMOS-2612",
                "country": "RUSSIA",
                "satNo": "68762",
                "rank": 2,
                "orbitRegime": "LEO",
            },
            {
                "commonName": "COSMOS-2613",
                "country": "RUSSIA",
                "satNo": "68763",
                "rank": 2,
                "orbitRegime": "LEO",
            },
            {
                "commonName": "COSMOS-2614",
                "country": "RUSSIA",
                "satNo": "68764",
                "rank": 2,
                "orbitRegime": "LEO",
            },
        ]
    )


@pytest.fixture
def client(fake_udl, tmp_path, monkeypatch):
    # readyz now probes real storage writability - isolate every test's
    # store to a throwaway tmp_path rather than the pytest cwd.
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    app = build_app(settings=make_settings(), udl_client=fake_udl)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}
