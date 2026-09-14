#!/usr/bin/env python3
"""Settle the two UDL behaviours Legion still carries as INFERENCE.

Makes a small number of authenticated calls against UDL and reports, as
evidence rather than assurance, whether `/udl/elset` accepts a direct
`satNo=` filter and what the `/udl/notification` `window_hours` parameter
actually returns. Both are flagged INFERENCE in `src/udl_client.py` and in
CLAUDE.md, and neither can be settled from the container this application is
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


def satno_verdict(status: int, count: int | None, asked_for: str) -> tuple[str, str]:
    """What a `satNo=` response proves about the filter.

    Three outcomes, and the middle one is the important one: a 200 that
    returns records for other satellites means the parameter was accepted and
    ignored, which is worse than a rejection because the chart would look
    entirely normal while plotting the wrong object.
    """
    if status == 0:
        # The first version of this said the response "was not a JSON array",
        # which is true and useless: the connection never happened. A message
        # that names the wrong cause sends the reader after the wrong fault.
        return UNKNOWN, NOT_REACHED
    if status >= 400:
        refused = (
            f"/udl/elset refused satNo with HTTP {status}. The filter is not "
            "supported and the client must not rely on it."
        )
        return FACT, refused
    if count is None:
        return UNKNOWN, "Response was not a JSON array; inspect it by hand."
    if count == 0:
        empty = (
            f"Accepted, but returned nothing for satNo={asked_for}. Either the "
            "filter works and there is no current element set, or it silently "
            "matched nothing. Retry with a satellite known to be current."
        )
        return INFERENCE, empty
    accepted = (
        f"Accepted and returned {count} record(s). Check every satNo in the "
        f"payload equals {asked_for}: a filter that is accepted and ignored is "
        "the dangerous case."
    )
    return FACT, accepted


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
        logging.error("%s", exc)
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
                "parameters": {k: v for k, v in params.items()},
                "status": status,
                "records": count_of(body),
                "note": note,
            }
        )
        time.sleep(PAUSE_SECONDS)
        return status, body, note

    reachable_status, _, reachable_note = call(
        "reachability", "/udl/elset", {"maxResults": 1}
    )
    if reachable_status == 0:
        logging.error("UDL is not reachable from here: %s", reachable_note)

    satno_status, satno_body, _ = call(
        "elset-satno-filter", "/udl/elset", {"satNo": args.norad, "maxResults": 5}
    )
    satno_marker, satno_finding = satno_verdict(
        satno_status, count_of(satno_body), str(args.norad)
    )

    _, short_body, _ = call(
        "notification-short-window", "/udl/notification", {"window_hours": 1}
    )
    _, long_body, _ = call(
        "notification-long-window", "/udl/notification", {"window_hours": 24}
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
                "question": "Does /udl/elset accept a direct satNo= filter?",
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
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        logging.info("Wrote %s", args.out)
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
        "a 4xx on satNo is a FACT that the filter is unsupported",
        FACT,
        satno_verdict(400, None, "49330")[0],
    )
    check(
        "T004",
        "an accepted satNo returning nothing is only an INFERENCE",
        INFERENCE,
        satno_verdict(200, 0, "49330")[0],
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
        "T011",
        "a file: base URL is refused before any request is made",
        True,
        _refuses("file:///etc/passwd"),
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
