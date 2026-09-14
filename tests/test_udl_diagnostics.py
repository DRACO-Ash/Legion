"""The diagnostics endpoint: what it says UDL said.

This module had no test file at all, which is how it came to report an HTTP
200 that UDL never sent. A deployment read "history not available at this
path, which is expected" with a 200 beside it, and both halves were this
application's own invention: `get_elset_history` had swallowed a 4xx, and the
probe's success path hard-coded the status.

That matters more here than almost anywhere else in the codebase. Every other
module is read by an analyst who can see the data and judge it. This one is
read by somebody who has nothing else to go on, so a fabricated value in it is
believed. The tests below are shaped around that: what a probe may claim, and
what it may not.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.app import build_app
from src.udl_client import ENDPOINT_ELSET_HISTORY, UDLError
from tests.conftest import FakeUDLClient, make_settings

SAT_NO = "40258"

ELSET = {
    "satNo": SAT_NO,
    "epoch": "2026-09-13T00:00:00.000000Z",
    "raan": 100.0,
    "argOfPerigee": 10.0,
    "meanAnomaly": 20.0,
    "meanMotion": 1.0027,
}


def _client(tmp_path, monkeypatch, udl) -> TestClient:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    return TestClient(build_app(settings=make_settings(), udl_client=udl))


def _report(tmp_path, monkeypatch, udl) -> dict:
    with _client(tmp_path, monkeypatch, udl) as client:
        response = client.get(f"/api/udl/diagnostics?sat_no={SAT_NO}")
    assert response.status_code == 200, response.text
    return response.json()


def _probe(report: dict, name: str) -> dict:
    found = [entry for entry in report["probes"] if entry["name"] == name]
    assert found, f"no {name} probe in {[p['name'] for p in report['probes']]}"
    return found[0]


def _working_udl(**kwargs) -> FakeUDLClient:
    return FakeUDLClient(
        satellites=[dict(ELSET, commonName="TEST", rank=1)],
        elset_history={SAT_NO: [ELSET]},
        **kwargs,
    )


def test_every_probe_runs_even_when_the_first_one_fails(tmp_path, monkeypatch):
    """One response is the whole picture, not the first thing to break.

    A probe that stopped at the first failure would answer the question the
    caller already knows and none of the ones they do not.
    """
    udl = FakeUDLClient(satellites=[], raise_error=UDLError("down"))
    report = _report(tmp_path, monkeypatch, udl)

    assert [entry["name"] for entry in report["probes"]] == [
        "jco_hrr_feed",
        "elset_latest",
        "elset_history",
    ]
    assert all(entry["ok"] is False for entry in report["probes"])


def test_a_successful_probe_never_claims_a_status_udl_did_not_send(
    tmp_path, monkeypatch
):
    """The defect this file was written for.

    The success path used to report `http_status: 200`. A probe calls a client
    method and receives a parsed object, not a response, so no status was ever
    observed. Calibrated by restoring the 200: this test fails.
    """
    report = _report(tmp_path, monkeypatch, _working_udl())

    for entry in report["probes"]:
        if entry["ok"]:
            assert entry["http_status"] is None, (
                f"{entry['name']} invented HTTP {entry['http_status']}"
            )


def test_a_failing_probe_reports_the_status_udl_did_send(tmp_path, monkeypatch):
    """The other half: a real status is carried through, not flattened."""
    udl = _working_udl(history_supported=False)
    report = _report(tmp_path, monkeypatch, udl)

    history = _probe(report, "elset_history")
    assert history["ok"] is False
    assert history["http_status"] == 404


def test_the_history_probe_bypasses_the_wrapper_that_swallows_a_4xx(
    tmp_path, monkeypatch
):
    """It calls the path raw, so a refusal is reported as a refusal.

    Through `get_elset_history` a 4xx comes back as None and the probe reads
    it as a success. That is correct for a chart, which falls back and still
    draws, and it is exactly wrong for a diagnostic.
    """
    udl = _working_udl(history_supported=False)
    _report(tmp_path, monkeypatch, udl)

    ops = [call for call in udl.calls if call["op"] == "probe"]
    assert ops, f"the history probe did not go raw: {udl.calls}"
    assert ops[0]["path"] == ENDPOINT_ELSET_HISTORY
    assert "get_elset_history" not in {call["op"] for call in udl.calls}


def test_the_history_probe_sends_the_epoch_qualifier_udl_requires(
    tmp_path, monkeypatch
):
    """Same query as the real call, or the probe reports on a different request.

    FACT, Ash against live UDL on 14 September 2026: /udl/elset answers 400
    without an `epoch`. A probe that omitted it would reproduce that 400 and
    report it as evidence the path is missing.
    """
    udl = _working_udl()
    _report(tmp_path, monkeypatch, udl)

    params = next(c for c in udl.calls if c["op"] == "probe")["params"]
    assert params["satNo"] == SAT_NO
    assert params["epoch"].startswith(">now-")


def test_a_history_refusal_is_reported_as_unresolved_not_as_expected(
    tmp_path, monkeypatch
):
    """The verdict states the status and stops short of explaining it.

    It used to call the refusal "expected", which was never established. The
    identical reading on /udl/elset turned out to be a wrong query, not an
    absent endpoint, so this one is open until somebody settles it.
    """
    report = _report(tmp_path, monkeypatch, _working_udl(history_supported=False))

    verdict = report["verdict"]
    assert "404" in verdict
    assert "not settled" in verdict
    assert "expected" not in verdict.lower()


def test_a_history_refusal_alone_does_not_read_as_a_broken_deployment(
    tmp_path, monkeypatch
):
    """Charts still work, so the verdict must not send anyone hunting.

    A 4xx there costs history depth and nothing else.
    """
    report = _report(tmp_path, monkeypatch, _working_udl(history_supported=False))

    assert _probe(report, "jco_hrr_feed")["ok"] is True
    assert _probe(report, "elset_latest")["ok"] is True
    assert "Charts still work" in report["verdict"]


def test_a_blocking_failure_names_the_probe_and_the_fix(tmp_path, monkeypatch):
    """A feed failure is blocking, and the verdict says which probe failed."""
    udl = FakeUDLClient(satellites=[], raise_error=UDLError("boom", status_code=401))
    report = _report(tmp_path, monkeypatch, udl)

    assert report["verdict"].startswith("jco_hrr_feed failed:")
    assert "rejected the credentials" in report["verdict"]


def test_everything_green_says_so_without_qualification(tmp_path, monkeypatch):
    """The one case where the answer is "not here"."""
    report = _report(tmp_path, monkeypatch, _working_udl())

    assert all(entry["ok"] for entry in report["probes"])
    assert "Every probe succeeded" in report["verdict"]
    assert _probe(report, "elset_history")["result"] == "1 element sets"


@pytest.mark.parametrize("field", ["username_len", "password_len"])
def test_the_report_carries_credential_lengths_and_never_a_credential(
    tmp_path, monkeypatch, field
):
    """The rule the token saga taught: name the difference, never the secret.

    Asserted against the whole serialised body rather than the credentials
    block, because a leak would not announce itself by appearing there.
    """
    # Distinctive values, because the default fixture username is "user",
    # which is a substring of "username_len" and made this pass for the wrong
    # reason in one direction and fail for the wrong reason in the other.
    settings = make_settings(
        udl_username="probe-account-zz", udl_password="probe-secret-zz"
    )
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    with TestClient(build_app(settings=settings, udl_client=_working_udl())) as client:
        body = client.get(f"/api/udl/diagnostics?sat_no={SAT_NO}").text

    assert field in body
    assert settings.udl_username not in body
    assert settings.udl_password not in body


def test_an_unconfigured_deployment_is_told_what_to_set(tmp_path, monkeypatch):
    """ "Not configured" and "refused" are different answers with different fixes."""
    udl = FakeUDLClient(configured=False)
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    settings = make_settings(udl_username="", udl_password="")
    with TestClient(build_app(settings=settings, udl_client=udl)) as client:
        report = client.get("/api/udl/diagnostics").json()

    assert report["credentials"]["configured"] is False
    assert "UDL_USERNAME" in report["verdict"]
