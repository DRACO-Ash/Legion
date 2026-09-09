"""Tests for the token difference diagnostic.

It exists because a live deployment sat at "both are 43 characters" with
nowhere to go. A non-breaking space or a look-alike hyphen is one character
and reads identically, so length cannot tell two values apart. This names the
kind of difference without revealing either value.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.app import build_app
from src.security import (
    NO_TOKEN_RECEIVED,
    TOKEN_CASE_ONLY,
    TOKEN_GENUINELY_DIFFERENT,
    TOKEN_LENGTH_DIFFERS,
    TOKEN_LOOK_ALIKES,
    TOKEN_MATCHES,
    TOKEN_NON_ASCII,
    describe_token_difference,
)

from .conftest import FakeUDLClient, make_settings

# A stand-in for secrets.token_urlsafe(32): 43 characters of the same alphabet.
REAL = ("aB3-_x" * 7 + "abc")[:43]
PATH = "/api/token-check"

# One non-breaking space inside an otherwise correct token. This is the case
# that defeated length comparison on a live deployment: 43 characters either
# way, 44 bytes one way, and identical on screen. Named once, because the
# platform's gate counts a repeated literal in the test tree too.
WITH_NBSP = REAL[:20] + "\u00a0" + REAL[21:]


@pytest.mark.parametrize(
    ("sent", "expected_verdict"),
    [
        (REAL, TOKEN_MATCHES),
        (WITH_NBSP, TOKEN_NON_ASCII),
        (REAL.replace("-", "‑", 1), TOKEN_LOOK_ALIKES),
        (REAL[:10] + "\u200b" + REAL[10:], TOKEN_LOOK_ALIKES),
        (REAL.upper(), TOKEN_CASE_ONLY),
        (REAL[:22], TOKEN_LENGTH_DIFFERS),
        (("zQ9-_p" * 7 + "xyz")[:43], TOKEN_GENUINELY_DIFFERENT),
        (None, NO_TOKEN_RECEIVED),
    ],
)
def test_each_kind_of_difference_is_named(sent, expected_verdict) -> None:
    assert describe_token_difference(sent, REAL)["verdict"] == expected_verdict


def test_a_match_is_reported_as_a_match() -> None:
    assert describe_token_difference(REAL, REAL)["matches"] is True


def test_the_shape_reports_bytes_as_well_as_characters() -> None:
    """The distinction that length alone cannot make: one non-breaking space
    is one character and two bytes."""
    described = describe_token_difference(WITH_NBSP, REAL)
    assert described["received"]["characters"] == 43
    assert described["received"]["utf8_bytes"] == 44
    assert described["received"]["ascii_only"] is False
    assert described["configured"]["utf8_bytes"] == 43


@pytest.mark.parametrize("sent", [REAL, REAL.upper(), REAL[:22], WITH_NBSP])
def test_neither_value_ever_appears_in_the_answer(sent) -> None:
    """The whole point: shapes and booleans, never a character of either."""
    rendered = repr(describe_token_difference(sent, REAL))
    assert REAL not in rendered
    assert REAL[:12] not in rendered
    assert sent[:12] not in rendered


def _app(token=REAL):
    return build_app(
        settings=make_settings(team_token=token), udl_client=FakeUDLClient()
    )


def test_the_route_answers_without_a_valid_token(tmp_path, monkeypatch) -> None:
    """It exists for the case where the token is refused, so gating it behind
    the token would make it useless."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    with TestClient(_app()) as client:
        response = client.get(PATH, headers={"Authorization": "Bearer " + REAL[:22]})
    assert response.status_code == 200
    body = response.json()
    assert body["matches"] is False
    assert body["verdict"] == TOKEN_LENGTH_DIFFERS


def test_the_route_reports_a_match(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    with TestClient(_app()) as client:
        body = client.get(PATH, headers={"Authorization": "Bearer " + REAL}).json()
    assert body["matches"] is True


def test_the_route_says_when_the_deployment_has_no_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    with TestClient(_app(token=None)) as client:
        body = client.get(PATH).json()
    assert body["matches"] is False
    assert "no TEAM_TOKEN configured" in body["verdict"]


def test_the_route_never_returns_the_configured_value(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    with TestClient(_app()) as client:
        raw = client.get(PATH, headers={"Authorization": "Bearer wrong"}).text
    assert REAL not in raw
    assert REAL[:12] not in raw
