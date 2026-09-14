#!/usr/bin/env python3
"""Settle the UDL behaviours Legion still carries as INFERENCE.

Makes a small number of authenticated calls against UDL and reports, as
evidence rather than assurance, what `/udl/notification`'s `window_hours`
parameter actually returns, and whether `/udl/elset` HONOURS a `satNo=`
filter rather than merely accepting it.

That second question changed on 14 September 2026, when Ash confirmed against
live UDL that `/udl/elset` requires an `epoch` qualifier and answers HTTP 400
without one, and that `satNo` is accepted alongside it. Acceptance is settled.
What is not settled is whether the filter is honoured, which is the dangerous
half: a parameter accepted and ignored returns a perfectly normal-looking
payload for the wrong satellites, and the chart drawn from it looks entirely
normal. So this script now reads every `satNo` in the response rather than
telling its reader to.

Every call here carries the epoch, because a probe that omitted it would earn
the 400 itself and report an unsupported filter: a message naming the wrong
cause, which is the mistake this script was already rewritten once to avoid.

Neither question can be settled from the container this application is
developed in, because `unifieddatalibrary.com:443` is refused at the
organisation proxy.

Run it from a machine that can reach UDL. Results go to stdout as JSON;
progress goes to stderr. Nothing it emits contains a credential.

    python scripts/udl_live_check.py --self-test
    python scripts/udl_live_check.py --norad 49330 --out udl-evidence.json

Network etiquette: one call at a time, an explicit timeout on each, a stated
pause between calls, and a User-Agent naming the tool.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import datetime
import getpass
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CRED_PATH: Path = Path.home() / ".config" / "phase_offset" / "credentials.ini"
DEFAULT_BASE_URL = "https://unifieddatalibrary.com"
USER_AGENT = "legion-udl-live-check/1.0"
PAUSE_SECONDS = 1.0
TIMEOUT_SECONDS = 30.0

FACT = "FACT"
INFERENCE = "INFERENCE"
UNKNOWN = "UNKNOWN"
ALLOWED_SCHEMES = ("https", "http")

# The notification filters the application actually sends. `window_hours` is
# Legion's own parameter name, not UDL's: the client turns it into a
# `createdAt` bound and sends three more filters that select the JCO HRR feed.
# The first version of this script sent `window_hours` straight through, which
# UDL does not have, and omitted the filters entirely, so it would have tested
# a parameter that does not exist against a feed it had not selected. A check
# that queries differently from the application it is checking proves
# something about the wrong thing.
NOTIFICATION_FILTERS: dict[str, str] = {
    "dataMode": "REAL",
    "msgType": "JCO-HRR-SATELLITES",
    "source": "JCO",
}


def hours_ago(hours: int) -> str:
    """UDL's relative time operator, written once.

    Mirrors `hours_ago` in src/udl_client.py. This script is stdlib-only and
    standalone by design, so it cannot import it; the duplication is between
    two trees deliberately, not within one.
    """
    return f">now-{hours} hours"


def notification_params(window_hours: int) -> dict[str, str]:
    """The query the application sends for a given window, reproduced exactly."""
    return {"createdAt": hours_ago(window_hours), **NOTIFICATION_FILTERS}


# FACT, Ash against live UDL on 14 September 2026: /udl/elset answers HTTP 400
# without an epoch bound. This mirrors ELSET_EPOCH_WINDOW_HOURS in
# src/udl_client.py so the probe asks what the application asks.
ELSET_EPOCH_WINDOW_HOURS = 168


def elset_params(**extra: object) -> dict[str, object]:
    """The mandatory epoch bound, plus whatever this particular probe adds."""
    return {"epoch": hours_ago(ELSET_EPOCH_WINDOW_HOURS), **extra}


NOT_REACHED = (
    "UDL could not be reached, so this check did not run. Nothing is settled "
    "either way."
)


def load_credentials(section: str = "udl") -> tuple[str, str]:
    """Return (username, password) for *section*, prompting interactively as fallback.

    Reads the shared credentials file with interpolation disabled so passwords
    containing ``%`` survive intact. Never logs or prints either value.
    """
    parser = configparser.ConfigParser(interpolation=None)
    try:
        found = parser.read(CRED_PATH, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        logging.warning("Could not read credentials file: %s", exc)
        found = []
    if found and parser.has_section(section):
        username = parser.get(section, "username", fallback="").strip()
        password = parser.get(section, "password", fallback="")
        if username and password:
            logging.info("Credentials loaded for section [%s]", section)
            return username, password
        logging.warning("Section [%s] present but incomplete", section)
    else:
        logging.warning("Credentials file absent or missing section [%s]", section)
    username = input(f"{section} username: ").strip()
    password = getpass.getpass(f"{section} password: ")
    return username, password


def credentials(non_interactive: bool) -> tuple[str, str]:
    """Environment first, then the shared file, matching the application.

    `src/config.py` reads `UDL_USERNAME` and `UDL_PASSWORD` before falling
    back to the credentials file, so this does the same: a script that
    authenticates differently from the application it is checking proves
    something about the wrong thing.
    """
    username = os.environ.get("UDL_USERNAME", "").strip()
    password = os.environ.get("UDL_PASSWORD", "")
    if username and password:
        logging.info("Credentials taken from the environment")
        return username, password
    if non_interactive:
        logging.error(
            "No UDL credentials in the environment and --non-interactive is set"
        )
        raise SystemExit(1)
    return load_credentials("udl")


# ---------------------------------------------------------------- task logic


def checked_url(candidate: str) -> str:
    """A base URL that is safe to hand to urlopen.

    `--base-url` is caller input, and `urlopen` will happily open `file:` or a
    custom scheme, so a mistyped flag could read a local file and report it as
    a UDL response. Refusing anything but http and https closes that.
    """
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        raise ValueError(
            f"Base URL must be http or https with a host, not {candidate!r}"
        )
    return candidate.rstrip("/")


def checked_out_path(candidate: str) -> Path:
    """An output path that is safe to write to.

    `--out` is caller input, and the same reasoning as `checked_url` applies:
    a mistyped or hostile flag should not be able to write outside the
    directory the operator is standing in. The path is resolved first, so
    `../` and a symlink in the middle are both taken into account rather than
    pattern-matched away, and then it must still sit under the working
    directory.

    Resolving before comparing is the whole of it. A check on the raw string
    can be walked straight past with a symlink, which is why this refuses on
    the resolved path and nothing else.
    """
    root = Path.cwd().resolve()
    resolved = (root / candidate).resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError(f"Output path must be inside {root}, not {candidate!r}")
    return resolved


def _request(url: str, auth_header: str) -> tuple[int, Any, str]:
    """One GET. Returns (status, parsed body or None, note).

    Every failure mode is named rather than raised past this point, because
    the whole purpose of the script is to report what happened, including a
    refusal.
    """
    request = urllib.request.Request(
        url, headers={"Authorization": auth_header, "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(raw), ""
            except json.JSONDecodeError:
                return response.status, None, "response was not JSON"
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTP error: {exc.reason}"
    except urllib.error.URLError as exc:
        return 0, None, f"could not connect: {exc.reason}"
    except TimeoutError:
        return 0, None, f"timed out after {TIMEOUT_SECONDS:.0f}s"


def _auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def count_of(body: Any) -> int | None:
    """How many records a UDL response carries, or None if it is not a list.

    UDL returns a bare JSON array on these endpoints. Anything else is worth
    recording as-is rather than coercing into a count that was never there.
    """
    return len(body) if isinstance(body, list) else None


def foreign_satnos(body: object, asked_for: str) -> list[str] | None:
    """Every satNo in the response that is not the one asked for.

    None means there was no array to read. An empty list means every record
    belongs to the requested satellite, which is the only shape that proves
    the filter was honoured rather than merely accepted.
    """
    if not isinstance(body, list):
        return None
    return sorted(
        {
            str(record.get("satNo"))
            for record in body
            if isinstance(record, dict) and str(record.get("satNo")) != str(asked_for)
        }
    )


def satno_verdict(status: int, body: object, asked_for: str) -> tuple[str, str]:
    """What a `satNo=` response proves about the filter.

    Acceptance is settled: Ash confirmed on 14 September 2026 that `satNo` is
    taken alongside the mandatory epoch. The open question is whether it is
    HONOURED, so this reads the payload instead of counting it. A parameter
    accepted and ignored is worse than one rejected, because the chart drawn
    from the wrong satellites looks entirely normal.
    """
    if status == 0:
        # The first version of this said the response "was not a JSON array",
        # which is true and useless: the connection never happened. A message
        # that names the wrong cause sends the reader after the wrong fault.
        return UNKNOWN, NOT_REACHED
    if status >= 400:
        # No longer read as "the filter is unsupported": a 400 here is much
        # more likely to be a malformed query, which is exactly what a missing
        # epoch produced for the life of this application.
        refused = (
            f"/udl/elset answered HTTP {status} for a query carrying both an "
            "epoch bound and satNo. That is a rejected request, not a verdict "
            "on the filter. Compare against the reachability check, which "
            "sends the epoch alone."
        )
        return INFERENCE, refused
    foreign = foreign_satnos(body, asked_for)
    if foreign is None:
        return UNKNOWN, "Response was not a JSON array; inspect it by hand."
    count = count_of(body)
    if count == 0:
        empty = (
            f"Accepted, but returned nothing for satNo={asked_for} inside a "
            f"{ELSET_EPOCH_WINDOW_HOURS}-hour window. Either the satellite has "
            "no recent element set or the filter silently matched nothing. "
            "Retry with a satellite known to be current."
        )
        return INFERENCE, empty
    if foreign:
        ignored = (
            f"ACCEPTED AND IGNORED. {count} record(s) came back and "
            f"{len(foreign)} other satNo(s) are among them: "
            f"{', '.join(foreign[:5])}. The client must not rely on this "
            "filter, and any chart built on it has been plotting the wrong "
            "objects."
        )
        return FACT, ignored
    honoured = (
        f"Honoured. All {count} record(s) carry satNo={asked_for} and no "
        "other. Read from the payload, not inferred from the status."
    )
    return FACT, honoured


def window_verdict(
    short_count: int | None, long_count: int | None, reached: bool = True
) -> tuple[str, str]:
    """What two window sizes prove about `window_hours` semantics.

    If a longer window returns more, the parameter selects a baseline. If the
    two are equal, it is either a delta feed or the feed is quiet, and the two
    cannot be told apart from counts alone, which is exactly why this is
    reported rather than concluded.
    """
    if not reached:
        return UNKNOWN, NOT_REACHED
    if short_count is None or long_count is None:
        return UNKNOWN, "One or both responses were not a JSON array."
    if long_count > short_count:
        baseline = (
            f"A longer window returned more records ({long_count} against "
            f"{short_count}), so window_hours selects a baseline over that "
            "period rather than deltas only."
        )
        return FACT, baseline
    if long_count == short_count == 0:
        quiet = (
            "Both windows were empty. The feed was quiet; this settles nothing. "
            "Re-run when the feed is active."
        )
        return UNKNOWN, quiet
    ambiguous = (
        f"Both windows returned {long_count} records. That is consistent with "
        "a delta feed and also with a quiet period. Counts alone cannot "
        "separate them: compare the record ids across two runs an hour apart."
    )
    return INFERENCE, ambiguous


def run(args: argparse.Namespace) -> int:
    """Execute the checks. Returns a process exit code."""
    username, password = credentials(args.non_interactive)
    header = _auth_header(username, password)
    try:
        base = checked_url(args.base_url)
    except ValueError as exc:
        logging.exception("Refusing the base URL: %s", exc)
        return 1
    checks: list[dict[str, Any]] = []

    def call(name: str, path: str, params: dict[str, Any]) -> tuple[int, Any, str]:
        url = f"{base}{path}?{urllib.parse.urlencode(params)}"
        logging.info("Calling %s", name)
        status, body, note = _request(url, header)
        logging.info("  %s -> HTTP %s %s", name, status, note)
        checks.append(
            {
                "check": name,
                "path": path,
                "parameters": dict(params),
                "status": status,
                "records": count_of(body),
                "note": note,
            }
        )
        time.sleep(PAUSE_SECONDS)
        return status, body, note

    reachable_status, _, reachable_note = call(
        "reachability", "/udl/elset", elset_params(maxResults=1)
    )
    if reachable_status == 0:
        logging.error("UDL is not reachable from here: %s", reachable_note)

    satno_status, satno_body, _ = call(
        "elset-satno-filter",
        "/udl/elset",
        elset_params(satNo=args.norad, maxResults=5),
    )
    satno_marker, satno_finding = satno_verdict(
        satno_status, satno_body, str(args.norad)
    )

    _, short_body, _ = call(
        "notification-short-window", "/udl/notification", notification_params(1)
    )
    _, long_body, _ = call(
        "notification-long-window", "/udl/notification", notification_params(24)
    )
    window_marker, window_finding = window_verdict(
        count_of(short_body), count_of(long_body), reached=reachable_status != 0
    )

    report = {
        "tool": Path(__file__).name,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "base_url": base,
        "reachable": reachable_status not in (0,),
        "checks": checks,
        "findings": [
            {
                "question": "Does /udl/elset HONOUR a satNo= filter, not just accept it?",
                "marker": satno_marker,
                "finding": satno_finding,
            },
            {
                "question": "What does the notification window_hours parameter select?",
                "marker": window_marker,
                "finding": window_finding,
            },
        ],
    }
    text = json.dumps(report, indent=2)
    if args.out:
        try:
            destination = checked_out_path(args.out)
        except ValueError as exc:
            logging.exception("Refusing the output path: %s", exc)
            return 1
        destination.write_text(text + "\n", encoding="utf-8")
        logging.info("Wrote %s", destination)
    else:
        print(text)
    return 0 if report["reachable"] else 1


# ---------------------------------------------------------------- self-test


def _refuses(candidate: str) -> bool:
    """True when `checked_url` rejects a candidate. Used by the self-test."""
    try:
        checked_url(candidate)
    except ValueError:
        return True
    return False


def _refuses_out(candidate: str) -> bool:
    """True when `checked_out_path` rejects a candidate."""
    try:
        checked_out_path(candidate)
    except ValueError:
        return True
    return False


def self_test() -> int:
    """Run built-in assertions and emit a JSON manifest. Exit 0 pass, 2 fail."""
    results: list[dict[str, object]] = []

    def check(
        test_id: str, description: str, expected: object, observed: object
    ) -> None:
        results.append(
            {
                "test_id": test_id,
                "description": description,
                "expected": repr(expected),
                "observed": repr(observed),
                "status": "pass" if expected == observed else "fail",
            }
        )

    check("T001", "a JSON array yields its length", 3, count_of([1, 2, 3]))
    check("T002", "a non-array yields no count", None, count_of({"a": 1}))
    check(
        "T003",
        "a 4xx on a query carrying the epoch settles nothing about the filter",
        INFERENCE,
        satno_verdict(400, None, "49330")[0],
    )
    check(
        "T004",
        "an accepted satNo returning nothing is only an INFERENCE",
        INFERENCE,
        satno_verdict(200, [], "49330")[0],
    )
    check(
        "T020",
        "a payload of only the asked-for satNo proves the filter is honoured",
        FACT,
        satno_verdict(200, [{"satNo": "49330"}, {"satNo": 49330}], "49330")[0],
    )
    check(
        "T021",
        "one foreign satNo in the payload means accepted and ignored",
        "ACCEPTED AND IGNORED",
        satno_verdict(200, [{"satNo": "49330"}, {"satNo": "40258"}], "49330")[1][:20],
    )
    check(
        "T022",
        "the foreign-satNo reader names the intruder, not the count",
        ["40258"],
        foreign_satnos([{"satNo": "49330"}, {"satNo": "40258"}], "49330"),
    )
    check(
        "T023",
        "the mandatory epoch bound travels on every elset call",
        hours_ago(ELSET_EPOCH_WINDOW_HOURS),
        elset_params(maxResults=1)["epoch"],
    )
    check(
        "T005",
        "a longer window returning more proves a baseline",
        FACT,
        window_verdict(2, 9)[0],
    )
    check(
        "T006",
        "equal windows cannot separate a delta feed from a quiet one",
        INFERENCE,
        window_verdict(4, 4)[0],
    )
    check(
        "T007",
        "two empty windows settle nothing",
        UNKNOWN,
        window_verdict(0, 0)[0],
    )
    check(
        "T008",
        "an unreachable endpoint is reported as unreachable, not as bad JSON",
        NOT_REACHED,
        satno_verdict(0, None, "49330")[1],
    )
    check(
        "T009",
        "the window check says the same when nothing was reached",
        NOT_REACHED,
        window_verdict(None, None, reached=False)[1],
    )
    check(
        "T013",
        "the window is sent as a createdAt bound, which is what UDL has",
        ">now-6 hours",
        notification_params(6)["createdAt"],
    )
    check(
        "T014",
        "the JCO HRR filters travel with it, so the right feed is selected",
        {"dataMode", "msgType", "source", "createdAt"},
        set(notification_params(6)),
    )
    check(
        "T011",
        "a file: base URL is refused before any request is made",
        True,
        _refuses("file:///etc/passwd"),
    )
    check(
        "T015",
        "an absolute --out path outside the working directory is refused",
        True,
        _refuses_out("/etc/passwd"),
    )
    check(
        "T016",
        "a traversing --out path is refused on the resolved path, not the text",
        True,
        _refuses_out("reports/../../escape.json"),
    )
    check(
        "T017",
        "an ordinary relative --out path is still accepted",
        False,
        _refuses_out("udl-check.json"),
    )
    check(
        "T012",
        "an https base URL is accepted and its trailing slash trimmed",
        "https://unifieddatalibrary.com",
        checked_url("https://unifieddatalibrary.com/"),
    )
    check(
        "T010",
        "the auth header is Basic and carries no plaintext",
        True,
        _auth_header("u", "p").startswith("Basic ")
        and "u:p" not in _auth_header("u", "p"),
    )

    manifest = {
        "tool": Path(__file__).name,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "tests": len(results),
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "failed": sum(1 for r in results if r["status"] == "fail"),
        "results": results,
    }
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["failed"] == 0 else 2


# ---------------------------------------------------------------- entry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the built-in test suite and emit a JSON manifest",
    )
    parser.add_argument("--verbose", action="store_true", help="debug-level logging")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("UDL_BASE_URL", DEFAULT_BASE_URL),
        help="UDL base URL (default: the application's own default)",
    )
    parser.add_argument(
        "--norad",
        default="49330",
        help="catalogue number to test the satNo filter with (default: SJ-21)",
    )
    parser.add_argument("--out", help="write the JSON report to this file")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="fail rather than prompt when no credentials are present",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.self_test:
        return self_test()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
