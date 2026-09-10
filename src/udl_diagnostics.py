"""Live probes that say why a UDL call failed.

This module exists because of a specific, repeated failure: the application
would report "UDL did not answer" and there was no way, from the deployment,
to tell a wrong password from a blocked network path from an endpoint whose
shape was never confirmed. The cause was always in the container log, and the
container log is not where the person trying to use the application is
looking.

The rule this follows is the one the team token saga taught, applied properly
this time: name the specific difference, never the secret. Every probe reports
which call it made, the HTTP status that came back, how long it took and what
kind of fault it was. No response from here ever contains a username, a
password, or any part of either. Lengths only, and only for the credentials
probe, which is what distinguishes "not configured" from "configured wrongly".
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Awaitable, Callable
from typing import Any

from src.udl_client import (
    ENDPOINT_ELSET,
    ENDPOINT_ELSET_HISTORY,
    ENDPOINT_NOTIFICATION,
    UDLError,
    UDLNotConfigured,
)

# What kind of thing went wrong, which is what decides who fixes it.
FAULT_NOT_CONFIGURED = "not_configured"
FAULT_AUTH = "auth"
FAULT_NOT_FOUND = "not_found"
FAULT_CLIENT = "client_error"
FAULT_UPSTREAM = "upstream_error"
FAULT_TIMEOUT = "timeout"
FAULT_TRANSPORT = "transport"
FAULT_SHAPE = "unexpected_shape"

FAULT_ADVICE = {
    FAULT_NOT_CONFIGURED: (
        "No UDL credentials in this deployment. Set UDL_USERNAME and "
        "UDL_PASSWORD in the Configuration tab, then restart the app so the "
        "worker reads them."
    ),
    FAULT_AUTH: (
        "UDL rejected the credentials. The username and password reached UDL "
        "and were refused, so the network path is fine and the values are "
        "wrong, expired, or not entitled to this endpoint."
    ),
    FAULT_NOT_FOUND: (
        "UDL answered, but has nothing at this path for this query. For "
        "/udl/elset/history that is expected and harmless: the app falls back "
        "to the latest element set. For the others it means the path or the "
        "filter is wrong."
    ),
    FAULT_CLIENT: (
        "UDL rejected the request itself, not the credentials. The query "
        "parameters or the filter syntax are wrong for this endpoint."
    ),
    FAULT_UPSTREAM: "UDL answered with a server error. The fault is upstream, not here.",
    FAULT_TIMEOUT: (
        "No answer within the timeout. Either UDL is slow, or nothing is "
        "reaching it: check the container's outbound network path before "
        "touching the credentials."
    ),
    FAULT_TRANSPORT: (
        "The connection itself failed, so nothing reached UDL. This is a "
        "network or egress-policy problem in the deployment, not a "
        "credentials problem."
    ),
    FAULT_SHAPE: (
        "UDL answered, but not in the shape this app expects. The endpoint "
        "exists and the credentials work; the parsing assumption is wrong."
    ),
}


def classify(exc: UDLError) -> str:
    """Name the kind of fault from the exception alone."""
    if isinstance(exc, UDLNotConfigured):
        return FAULT_NOT_CONFIGURED
    status_code = exc.status_code
    if status_code is None:
        message = str(exc).lower()
        if "timed out" in message:
            return FAULT_TIMEOUT
        if "unexpected response" in message:
            return FAULT_SHAPE
        return FAULT_TRANSPORT
    if status_code in (401, 403):
        return FAULT_AUTH
    if status_code == 404:
        return FAULT_NOT_FOUND
    if 400 <= status_code < 500:
        return FAULT_CLIENT
    return FAULT_UPSTREAM


async def _probe(
    name: str,
    path: str,
    call: Callable[[], Awaitable[Any]],
    describe: Callable[[Any], str],
) -> dict[str, Any]:
    """Run one call and report what happened, whatever happens.

    A probe never raises. The whole point is to return a full picture in one
    response, so a failing first probe must not hide the state of the rest.
    """
    started = time.monotonic()
    try:
        result = await call()
    except UDLError as exc:
        fault = classify(exc)
        return {
            "name": name,
            "path": path,
            "ok": False,
            "http_status": exc.status_code,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "result": None,
            "fault": fault,
            "detail": str(exc),
            "advice": FAULT_ADVICE[fault],
        }
    return {
        "name": name,
        "path": path,
        "ok": True,
        "http_status": 200,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "result": describe(result),
        "fault": None,
        "detail": None,
        "advice": None,
    }


def _describe_feed(satellites: list[dict[str, Any]]) -> str:
    ranked = [s for s in satellites if s.get("rank") is not None]
    return f"{len(satellites)} entries in the feed, {len(ranked)} carrying a rank"


def _describe_elset(record: dict[str, Any] | None) -> str:
    if record is None:
        return "answered, but holds no element set for this satNo"
    return f"latest element set, epoch {record.get('epoch') or 'not stated'}"


def _describe_history(records: list[dict[str, Any]] | None) -> str:
    if records is None:
        return (
            "not available at this path, which is expected: the app falls back "
            "to the latest element set"
        )
    return f"{len(records)} element sets"


def _verdict(credentials: dict[str, Any], probes: list[dict[str, Any]]) -> str:
    if not credentials["configured"]:
        return FAULT_ADVICE[FAULT_NOT_CONFIGURED]
    failed = [probe for probe in probes if not probe["ok"]]
    if not failed:
        return (
            "Every probe succeeded. UDL is reachable, the credentials work, "
            "and the endpoints answer in the shape this app expects. A chart "
            "that still fails is not failing here."
        )
    # History returning 4xx is a designed fallback, not a fault, so it never
    # decides the verdict on its own.
    blocking = [
        probe
        for probe in failed
        if not (probe["name"] == "elset_history" and probe["fault"] == FAULT_NOT_FOUND)
    ]
    if not blocking:
        return (
            "Element-set history is not available at that path, which is "
            "expected and handled: charts fall back to the latest element set "
            "and show a single point per object."
        )
    first = blocking[0]
    return f"{first['name']} failed: {first['advice']}"


async def run_diagnostics(
    client: Any,
    *,
    sat_no: str,
    hrr_window_hours: int,
    base_url: str,
    username: str | None,
    password: str | None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Probe every UDL call the charts depend on, and report all of them.

    Lengths of the credentials, never the values: the length is what separates
    "nothing configured" from "configured but refused", and that is the only
    question a caller needs answered here.
    """
    credentials = {
        "configured": bool(username and password),
        "username_len": len(username or ""),
        "password_len": len(password or ""),
    }
    probes = [
        await _probe(
            "jco_hrr_feed",
            ENDPOINT_NOTIFICATION,
            lambda: client.fetch_jco_hrr(window_hours=hrr_window_hours),
            _describe_feed,
        ),
        await _probe(
            "elset_latest",
            ENDPOINT_ELSET,
            lambda: client.get_elset(sat_no),
            _describe_elset,
        ),
        await _probe(
            "elset_history",
            ENDPOINT_ELSET_HISTORY,
            lambda: client.get_elset_history(sat_no),
            _describe_history,
        ),
    ]
    return {
        "generated_at": (now or dt.datetime.now(dt.UTC)).isoformat(),
        "base_url": base_url,
        "sat_no_probed": sat_no,
        "credentials": credentials,
        "probes": probes,
        "verdict": _verdict(credentials, probes),
    }


# What a caller is told when a UDL-backed route fails. Built from the fault
# kind and the status code only, never from the exception's own text: a
# message assembled upstream could one day carry a URL, a query or worse, and
# "never echo the upstream message" is a property worth keeping. These strings
# say as much as the log does about the cause, and nothing about the secret.
SAFE_DETAIL = {
    FAULT_NOT_CONFIGURED: "UDL is not configured on this deployment.",
    FAULT_AUTH: "UDL rejected the credentials.",
    FAULT_NOT_FOUND: "UDL holds nothing at that path for this query.",
    FAULT_CLIENT: "UDL rejected the request, not the credentials.",
    FAULT_UPSTREAM: "UDL returned a server error.",
    FAULT_TIMEOUT: "UDL did not answer within the timeout.",
    FAULT_TRANSPORT: "The connection to UDL failed, so nothing reached it.",
    FAULT_SHAPE: "UDL answered in a shape this app does not expect.",
}

DIAGNOSTICS_HINT = "Call /api/udl/diagnostics for the full picture."


def safe_detail(exc: UDLError) -> str:
    """One sentence naming the cause, plus the status when there was one."""
    fault = classify(exc)
    parts = [SAFE_DETAIL[fault]]
    if exc.status_code is not None:
        parts.append(f"HTTP {exc.status_code}.")
    parts.append(DIAGNOSTICS_HINT)
    return " ".join(parts)
