"""The logging standard, asserted on what a real handler writes.

Two histories meet here. Up to 0.4.1 the audit trail was silently dropped,
and the tests meant to cover it asserted through `caplog`, which installs its
own handler and so passed regardless. At 0.19.0 the platform's Logging check
found that nothing reached stdout, seven lines reached stderr and no line
carried the request id, while every test here passed, because none of them
looked at gunicorn. So every test below reads a real stream, and the last one
runs real gunicorn the way the platform does.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import gunicorn.config
import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src import gunicorn_conf
from src.app import _STDOUT_HANDLER_NAME, build_app, configure_logging
from src.logging_standard import (
    AUDIT_LOGGER_NAME as STANDARD_AUDIT_LOGGER,
)
from src.logging_standard import (
    OUTCOME_ATTRIBUTE,
    REQUEST_ID_ATTRIBUTE,
    ROUTE_ATTRIBUTE,
    STATUS_ATTRIBUTE,
    USER_AGENT_ATTRIBUTE,
    USER_EMAIL_ATTRIBUTE,
    JsonLineFormatter,
    RequestLogMiddleware,
    outcome,
    server_logconfig,
)
from src.store import APP_LOGGER_NAME, AUDIT_LOGGER_NAME, TrackedSystemsStore

from .conftest import FakeUDLClient, make_seed_record, make_settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTHZ_LINE = "GET /healthz 200"
FIELDS = {"timestamp", "severity_text", "severity_number", "body", "attributes"}
SEED = [
    make_seed_record(
        family_id="log-fam",
        family_title="Logging Family",
        designator="LOG-1",
        catalogue_name="LOGSAT-1",
        launch_year=2021,
    )
]


@pytest.fixture
def logging_state():
    """Snapshot and restore the loggers `configure_logging` touches."""
    root = logging.getLogger()
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    saved = (list(root.handlers), root.level, app_logger.level, audit_logger.level)
    yield
    root.handlers = saved[0]
    root.setLevel(saved[1])
    app_logger.setLevel(saved[2])
    audit_logger.setLevel(saved[3])


def _capture(monkeypatch, level: str | None = None) -> io.StringIO:
    """Configure logging, then point the real installed handler at a buffer."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if h.name != _STDOUT_HANDLER_NAME]
    configure_logging(level)
    handler = next(h for h in root.handlers if h.name == _STDOUT_HANDLER_NAME)
    assert isinstance(handler, logging.StreamHandler)
    stream = io.StringIO()
    handler.setStream(stream)
    return stream


def _lines(stream: io.StringIO) -> list[dict]:
    """Every line must be one JSON object in the platform's shape."""
    parsed = []
    for line in stream.getvalue().splitlines():
        record = json.loads(line)
        assert set(record) == FIELDS, record
        assert all(not isinstance(v, dict) for v in record["attributes"].values())
        parsed.append(record)
    return parsed


def test_every_level_maps_to_the_standard_severity_pair(logging_state, monkeypatch):
    stream = _capture(monkeypatch, level="DEBUG")
    probe = logging.getLogger(f"{APP_LOGGER_NAME}.probe")
    for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
        probe.log(level, "x")
    probe.critical("x")
    pairs = [(r["severity_text"], r["severity_number"]) for r in _lines(stream)]
    assert pairs == [
        ("DEBUG", 5),
        ("INFO", 9),
        ("WARN", 13),
        ("ERROR", 17),
        ("FATAL", 21),
    ]


def test_the_timestamp_is_utc_to_the_millisecond(logging_state, monkeypatch):
    stream = _capture(monkeypatch)
    logging.getLogger(f"{APP_LOGGER_NAME}.probe").info("x")
    stamp = _lines(stream)[0]["timestamp"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", stamp), stamp
    parsed = dt.datetime.fromisoformat(stamp)
    assert abs((dt.datetime.now(dt.UTC) - parsed).total_seconds()) < 5


def test_an_exception_travels_as_attributes(logging_state, monkeypatch):
    stream = _capture(monkeypatch)
    try:
        raise ValueError("bad epoch")
    except ValueError:
        logging.getLogger(f"{APP_LOGGER_NAME}.probe").exception("failed")
    attributes = _lines(stream)[0]["attributes"]
    assert attributes["exception.type"] == "ValueError"
    assert attributes["exception.message"] == "bad epoch"
    assert "Traceback" in attributes["exception.stacktrace"]


def test_a_nested_attribute_is_flattened_to_text(logging_state, monkeypatch):
    stream = _capture(monkeypatch)
    logging.getLogger(f"{APP_LOGGER_NAME}.probe").info(
        "x", extra={"attributes": {"shape": {"a": 1}, "ids": ["p", "q"]}}
    )
    attributes = _lines(stream)[0]["attributes"]
    assert attributes["shape"] == '{"a": 1}'
    assert attributes["ids"] == ["p", "q"]


def test_an_audit_line_is_written_once_with_its_fields(logging_state, monkeypatch):
    stream = _capture(monkeypatch)
    logging.getLogger(AUDIT_LOGGER_NAME).info(
        json.dumps({"event": "system_created", "actor": "203.0.113.5"})
    )
    lines = _lines(stream)
    assert len(lines) == 1
    assert lines[0]["body"] == "audit system_created"
    assert lines[0]["attributes"]["legion.audit.actor"] == "203.0.113.5"


def test_raising_log_level_never_silences_the_audit_trail(logging_state, monkeypatch):
    """LOG_LEVEL is for diagnostics. The audit trail is a compliance record."""
    stream = _capture(monkeypatch, level="WARNING")
    logging.getLogger(f"{APP_LOGGER_NAME}.store").info("diagnostic noise")
    logging.getLogger(AUDIT_LOGGER_NAME).info(json.dumps({"event": "probe"}))
    assert [r["body"] for r in _lines(stream)] == ["audit probe"]


def test_third_party_info_stays_out(logging_state, monkeypatch):
    """httpx logs each UDL request at INFO with its query string."""
    stream = _capture(monkeypatch)
    logging.getLogger("httpx").info("HTTP Request: GET /udl/elset?satNo=1")
    logging.getLogger("httpx").warning("kept")
    assert [r["body"] for r in _lines(stream)] == ["kept"]


def test_configure_logging_is_idempotent(logging_state, monkeypatch):
    _capture(monkeypatch)
    for _ in range(3):
        configure_logging()
    named = [h for h in logging.getLogger().handlers if h.name == _STDOUT_HANDLER_NAME]
    assert len(named) == 1


def test_unknown_log_level_falls_back_to_info(logging_state, monkeypatch):
    stream = _capture(monkeypatch, level="NOT_A_LEVEL")
    logging.getLogger(f"{APP_LOGGER_NAME}.store").info("still visible")
    assert [r["body"] for r in _lines(stream)] == ["still visible"]


def test_log_level_env_var_is_honoured(logging_state, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")
    configure_logging()
    assert logging.getLogger(APP_LOGGER_NAME).level == logging.WARNING


def test_the_audit_logger_name_is_the_same_in_both_modules():
    """`logging_standard` repeats the name so gunicorn's master can import it
    without importing the store. Two copies must agree."""
    assert STANDARD_AUDIT_LOGGER == AUDIT_LOGGER_NAME


def test_privileged_action_writes_one_parsable_audit_line(
    logging_state, monkeypatch, tmp_path
):
    """End to end: a real store write, through a real handler, to a stream."""
    stream = _capture(monkeypatch)
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    store = TrackedSystemsStore(seed_records=SEED)
    created = store.create(
        {**SEED[0], "catalogue_name": "AUDITSAT-9"}, actor="203.0.113.5"
    )
    audits = [r for r in _lines(stream) if r["body"].startswith("audit ")]
    assert len(audits) == 1
    assert audits[0]["attributes"]["legion.audit.event"] == "system_created"
    assert audits[0]["attributes"]["legion.audit.record_id"] == created["id"]


def test_a_request_line_carries_the_request_id_and_never_the_query(
    logging_state, monkeypatch, tmp_path
):
    """The check sends an X-Request-Id and looks for it in the attributes."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    stream = _capture(monkeypatch)
    app = build_app(settings=make_settings(), udl_client=FakeUDLClient())
    with TestClient(app) as client:
        client.get(
            "/api/systems?q=secretquery",
            headers={
                "X-Request-Id": "req-123",
                "X-Auth-Request-Email": "analyst@example.org",
                "Authorization": "Bearer shh",
                "Cookie": "session=shh",
            },
        )
    text = stream.getvalue()
    requests = [r for r in _lines(stream) if r["body"].startswith("GET ")]
    assert requests[-1]["body"] == "GET /api/systems 200"
    assert requests[-1]["attributes"][REQUEST_ID_ATTRIBUTE] == ["req-123"]
    assert requests[-1]["attributes"][USER_EMAIL_ATTRIBUTE] == "analyst@example.org"
    for forbidden in ("secretquery", "Bearer", "shh"):
        assert forbidden not in text


def test_every_line_written_during_a_request_carries_its_id(
    logging_state, monkeypatch, tmp_path
):
    """The audit line is written in a threadpool, inside the request."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    stream = _capture(monkeypatch)
    app = build_app(settings=make_settings(), udl_client=FakeUDLClient())
    with TestClient(app) as client:
        record_id = client.get("/api/systems").json()["systems"][0]["id"]
        response = client.patch(
            f"/api/systems/{record_id}",
            json={"notes": "logging check"},
            headers={"X-Request-Id": "req-write"},
        )
    assert response.status_code == 200
    audits = [r for r in _lines(stream) if r["body"] == "audit system_updated"]
    assert audits[0]["attributes"][REQUEST_ID_ATTRIBUTE] == ["req-write"]


def test_every_line_in_a_request_names_its_path_method_and_user_agent(
    logging_state, monkeypatch, tmp_path
):
    """The 0.19.2 warning: lines written while handling a request lacked
    `user_agent.original`, and the audit line lacked the path and method too."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    stream = _capture(monkeypatch)
    app = build_app(settings=make_settings(), udl_client=FakeUDLClient())
    with TestClient(app) as client:
        record_id = client.get("/api/systems").json()["systems"][0]["id"]
        client.patch(
            f"/api/systems/{record_id}",
            json={"notes": "agent check"},
            headers={"X-Request-Id": "req-ua", "User-Agent": "probe/1.0"},
        )
    during = [
        r
        for r in _lines(stream)
        if r["attributes"].get(REQUEST_ID_ATTRIBUTE) == ["req-ua"]
    ]
    assert {r["body"] for r in during} >= {
        "audit system_updated",
        f"PATCH /api/systems/{record_id} 200",
    }
    for line in during:
        attributes = line["attributes"]
        assert attributes[USER_AGENT_ATTRIBUTE] == "probe/1.0", line
        assert attributes["url.path"] == f"/api/systems/{record_id}", line
        assert attributes["http.request.method"] == "PATCH", line


def test_the_request_line_carries_status_and_outcome(
    logging_state, monkeypatch, tmp_path
):
    """The check calls this the request's audit line and wants the path,
    method, status, user agent and outcome on it."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    stream = _capture(monkeypatch)
    app = build_app(settings=make_settings(), udl_client=FakeUDLClient())
    with TestClient(app) as client:
        client.get("/healthz", headers={"User-Agent": "probe/1.0"})
        client.get("/api/systems/does-not-exist")
    by_body = {r["body"]: r["attributes"] for r in _lines(stream)}
    ok = by_body[HEALTHZ_LINE]
    missing = by_body["GET /api/systems/does-not-exist 404"]
    assert ok[STATUS_ATTRIBUTE] == 200
    assert ok[OUTCOME_ATTRIBUTE] == "success"
    assert missing[OUTCOME_ATTRIBUTE] == "failure"
    for attributes in (ok, missing):
        assert {"url.path", "http.request.method", USER_AGENT_ATTRIBUTE} <= set(
            attributes
        )
    assert ok[ROUTE_ATTRIBUTE] == "/healthz"
    assert ROUTE_ATTRIBUTE not in missing or missing[ROUTE_ATTRIBUTE].startswith("/")


def test_an_absent_header_leaves_its_attribute_out(logging_state, monkeypatch):
    """The standard: "Do not write null, an empty string or an empty array."
    0.19.3 wrote an empty user agent, on a guess the standard contradicts."""
    stream = _capture(monkeypatch)
    app = Starlette(routes=[Route("/ok", _ok)])
    app.add_middleware(RequestLogMiddleware)
    with TestClient(app) as client:
        client.get("/ok", headers={"User-Agent": ""})
    request = next(r for r in _lines(stream) if r["body"] == "GET /ok 200")
    for absent in (USER_AGENT_ATTRIBUTE, REQUEST_ID_ATTRIBUTE, USER_EMAIL_ATTRIBUTE):
        assert absent not in request["attributes"]
    assert "" not in request["attributes"].values()


def test_an_audit_line_states_its_outcome(logging_state, monkeypatch, tmp_path):
    """Written only after the write reached disk, so the outcome is known."""
    stream = _capture(monkeypatch)
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    store = TrackedSystemsStore(seed_records=SEED)
    store.create({**SEED[0], "catalogue_name": "AUDITSAT-8"}, actor="tester")
    audit = next(r for r in _lines(stream) if r["body"].startswith("audit "))
    assert audit["attributes"][OUTCOME_ATTRIBUTE] == "success"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, "success"),
        (307, "success"),
        (399, "success"),
        (400, "failure"),
        (429, "failure"),
        (500, "failure"),
    ],
)
def test_outcome_counts_a_refused_request_as_a_failure(status, expected):
    assert outcome(status) == expected


def test_a_request_without_an_id_invents_none(logging_state, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    stream = _capture(monkeypatch)
    app = build_app(settings=make_settings(), udl_client=FakeUDLClient())
    with TestClient(app) as client:
        client.get("/healthz")
    request = next(r for r in _lines(stream) if r["body"] == HEALTHZ_LINE)
    assert REQUEST_ID_ATTRIBUTE not in request["attributes"]


def _boom(request):
    raise RuntimeError("handler failed")


def _ok(request):
    return PlainTextResponse("fine")


def test_an_unhandled_error_is_one_line_with_the_request_id(logging_state, monkeypatch):
    """Logged once, here, with the id, rather than again by uvicorn after the
    request context had gone."""
    stream = _capture(monkeypatch)
    app = Starlette(routes=[Route("/boom", _boom), Route("/ok", _ok)])
    app.add_middleware(RequestLogMiddleware)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert (
            client.get("/boom", headers={"X-Request-Id": "req-err"}).status_code == 500
        )
    errors = [r for r in _lines(stream) if r["severity_text"] == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["attributes"]["exception.type"] == "RuntimeError"
    assert errors[0]["attributes"][REQUEST_ID_ATTRIBUTE] == ["req-err"]


def test_gunicorn_routes_its_own_lines_to_the_standard_handler():
    config = server_logconfig()
    assert config["loggers"]["gunicorn.error"]["handlers"] == [_STDOUT_HANDLER_NAME]
    assert config["loggers"]["gunicorn.error"]["propagate"] is False
    assert config["handlers"][_STDOUT_HANDLER_NAME]["stream"] == "ext://sys.stdout"
    assert config["root"]["level"] == "WARNING"


def test_the_gunicorn_config_sets_only_the_settings_it_means_to():
    """Gunicorn reads every top-level name that matches a setting. Importing
    the builder as `logconfig` made gunicorn treat a function as a file path
    and refuse to start; found by running it, not by reading it."""
    settings = set(gunicorn.config.make_settings())
    public = {name for name in vars(gunicorn_conf) if not name.startswith("_")}
    assert public & settings == {"logconfig_dict", "accesslog"}
    assert gunicorn_conf.accesslog is None


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _gunicorn(tmp_path, port: int) -> subprocess.Popen:
    env = {
        **os.environ,
        "ALLOWED_ORIGIN": "http://localhost:8080",
        "STORAGE_MOUNT_PATH": str(tmp_path),
        "UDL_USERNAME": "x",
        "UDL_PASSWORD": "y",
    }
    command = [
        sys.executable, "-m", "gunicorn", "src.app:app", "-c", "src/gunicorn_conf.py",
        "-k", "uvicorn.workers.UvicornWorker", "-b", f"127.0.0.1:{port}",
    ]  # fmt: skip
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _ask_until_answered(url: str) -> bool:
    request = urllib.request.Request(
        url, headers={"X-Request-Id": "gun-1", "User-Agent": "gun-probe/1.0"}
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(request, timeout=2).read()
            return True
        except OSError:
            time.sleep(0.25)
    return False


def test_real_gunicorn_writes_only_standard_lines_to_stdout(tmp_path):
    """The platform's check, reproduced: start the server the way the
    container does, send a request with an X-Request-Id, and read both
    streams. At 0.19.0 this would have found seven lines on stderr.

    The port is chosen here and the server polled, never read for its port
    line: the first version blocked on stdout and hung, rather than failed,
    when a sabotage sent gunicorn's lines to stderr instead.
    """
    port = _free_port()
    server = _gunicorn(tmp_path, port)
    try:
        answered = _ask_until_answered(f"http://127.0.0.1:{port}/healthz")
    finally:
        server.terminate()
        out, err = server.communicate(timeout=20)
    assert answered, f"gunicorn never answered; stderr: {err[:500]}"
    assert err == "", f"stderr must be empty, got: {err[:500]}"
    lines = [json.loads(line) for line in out.splitlines()]
    assert all(set(line) == FIELDS for line in lines)
    tagged = [
        line
        for line in lines
        if line["attributes"].get(REQUEST_ID_ATTRIBUTE) == ["gun-1"]
        and line["body"] == HEALTHZ_LINE
    ]
    assert tagged, "no request line carried the X-Request-Id"
    assert tagged[0]["attributes"][USER_AGENT_ATTRIBUTE] == "gun-probe/1.0"
    assert tagged[0]["attributes"][OUTCOME_ATTRIBUTE] == "success"
    assert tagged[0]["attributes"][ROUTE_ATTRIBUTE] == "/healthz"


# The rules below come from the App Store's "Logging requirements" page. Each
# test names the rule it holds.

KNOWN_KEYS = {
    "http.request.header.x-request-id",
    "http.request.method",
    "http.request.method_original",
    "http.response.status_code",
    "http.route",
    "url.path",
    "user.email",
    "user_agent.original",
    "event.outcome",
    "otel.event.name",
    "code.function.name",
    "exception.type",
    "exception.message",
    "exception.stacktrace",
}


def _record(message: str = "m", **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        "udl_tactics_app", logging.INFO, __file__, 1, message, (), None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonLineFormatter().format(record))


def _app_lines(monkeypatch, tmp_path, call) -> list[dict]:
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    stream = _capture(monkeypatch)
    app = build_app(settings=make_settings(), udl_client=FakeUDLClient())
    with TestClient(app) as client:
        call(client)
    return _lines(stream)


def test_the_request_line_names_the_route_that_matched(
    logging_state, monkeypatch, tmp_path
):
    """`http.route` is the route template, never the path with its values."""

    def call(client):
        record_id = client.get("/api/systems").json()["systems"][0]["id"]
        client.patch(f"/api/systems/{record_id}", json={"notes": "route"})

    lines = _app_lines(monkeypatch, tmp_path, call)
    patch = next(r for r in lines if r["body"].startswith("PATCH "))
    route = patch["attributes"][ROUTE_ATTRIBUTE]
    assert route.startswith("/api/systems/{")
    assert route != patch["attributes"]["url.path"]


def test_an_unknown_method_is_other_with_the_original_kept(logging_state, monkeypatch):
    stream = _capture(monkeypatch)
    app = Starlette(routes=[Route("/ok", _ok, methods=["PROPFIND"])])
    app.add_middleware(RequestLogMiddleware)
    with TestClient(app) as client:
        client.request("PROPFIND", "/ok")
    request = next(r for r in _lines(stream) if STATUS_ATTRIBUTE in r["attributes"])
    assert request["attributes"]["http.request.method"] == "_OTHER"
    assert request["attributes"]["http.request.method_original"] == "PROPFIND"


async def _half_sent(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"part", "more_body": True})
    raise ConnectionResetError("client went away")


def test_a_response_that_never_finished_has_outcome_unknown(logging_state, monkeypatch):
    stream = _capture(monkeypatch)
    # No `with`: that would run a lifespan this bare ASGI app does not speak.
    TestClient(RequestLogMiddleware(_half_sent), raise_server_exceptions=False).get(
        "/half"
    )
    request = next(r for r in _lines(stream) if STATUS_ATTRIBUTE in r["attributes"])
    assert request["attributes"][OUTCOME_ATTRIBUTE] == "unknown"


def test_long_values_are_cut_and_marked():
    line = _format(
        _record(
            "b" * 2500,
            attributes={"legion.note": "n" * 300, "legion.list": list("abcdef")},
        )
    )
    attributes = line["attributes"]
    assert line["body"] == "b" * 2000 + "[truncated]"
    assert attributes["legion.note"] == "n" * 256 + "[truncated]"
    assert attributes["legion.list"] == list("abcd")
    assert attributes["appstore.log.truncated"] is True


def test_a_short_line_is_not_marked_truncated():
    assert "appstore.log.truncated" not in _format(_record("short"))["attributes"]


def test_an_exception_is_bounded_and_fully_qualified():
    try:
        json.loads("{" + "x" * 1500)
    except json.JSONDecodeError:
        exc_info = sys.exc_info()
    record = _record("failed")
    record.exc_info = exc_info
    record.exc_info = (exc_info[0], exc_info[0]("m" * 1500, "doc", 0), exc_info[2])
    attributes = _format(record)["attributes"]
    assert attributes["exception.type"] == "json.decoder.JSONDecodeError"
    assert attributes["exception.message"].endswith("[truncated]")
    assert len(attributes["exception.message"]) <= 1000 + len("[truncated]")


def test_a_long_stacktrace_keeps_both_ends():
    """Python puts the exception last, so the cut is in the middle."""
    try:
        raise ValueError("x" * 5000 + " the real cause")
    except ValueError:
        exc_info = sys.exc_info()
    record = _record("failed")
    record.exc_info = exc_info
    trace = _format(record)["attributes"]["exception.stacktrace"]
    assert "\n[truncated]\n" in trace
    assert trace.startswith("Traceback")
    assert trace.rstrip().endswith("the real cause")


def test_an_uncaught_exception_is_a_fatal_contract_line(logging_state, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    stream = _capture(monkeypatch)
    try:
        raise RuntimeError("boom at the top")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    fatal = [r for r in _lines(stream) if r["severity_text"] == "FATAL"]
    assert len(fatal) == 1
    assert fatal[0]["attributes"]["exception.message"] == "boom at the top"


def test_a_crashed_thread_is_an_error_line(logging_state, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    stream = _capture(monkeypatch)

    def crash():
        raise LookupError("thread failed")

    thread = threading.Thread(target=crash)
    thread.start()
    thread.join()
    errors = [r for r in _lines(stream) if r["severity_text"] == "ERROR"]
    assert errors[0]["attributes"]["exception.type"] == "LookupError"


def _events(lines: list[dict], name: str) -> list[dict]:
    return [r for r in lines if r["attributes"].get("otel.event.name") == name]


def test_start_and_stop_are_security_events_whatever_the_log_level(
    logging_state, monkeypatch, tmp_path
):
    """LOG_LEVEL=WARNING must not silence a compliance record. Set in the
    environment, because build_app configures logging again from it: a level
    passed to configure_logging alone was reset to INFO and proved nothing."""
    monkeypatch.setenv("STORAGE_MOUNT_PATH", str(tmp_path))
    stream = _capture(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    app = build_app(settings=make_settings(), udl_client=FakeUDLClient())
    with TestClient(app):
        pass
    lines = _lines(stream)
    for name in ("appstore.app.start", "appstore.app.stop"):
        event = _events(lines, name)
        assert len(event) == 1, name
        assert event[0]["attributes"]["event.outcome"] == "success"
        assert event[0]["attributes"]["code.function.name"]
        assert event[0]["severity_text"] == "INFO"


def test_a_briefing_is_logged_as_an_export(logging_state, monkeypatch, tmp_path):
    def call(client):
        record_id = client.get("/api/systems").json()["systems"][0]["id"]
        assert client.get(f"/api/briefing?ids={record_id}").status_code == 200

    export = _events(_app_lines(monkeypatch, tmp_path, call), "appstore.data.export")
    assert len(export) == 1
    assert export[0]["attributes"]["legion.briefing.subjects"] == 1


def test_every_key_is_a_standard_one_or_carries_the_app_prefix(
    logging_state, monkeypatch, tmp_path
):
    """No key invented inside an OpenTelemetry namespace. 0.19.3 wrote
    `audit.*`, `logger.name` and `http.server.request.duration_ms`."""

    def call(client):
        record_id = client.get("/api/systems").json()["systems"][0]["id"]
        client.patch(
            f"/api/systems/{record_id}",
            json={"notes": "keys"},
            headers={"X-Request-Id": "k", "X-Auth-Request-Email": "a@example.org"},
        )
        client.get(f"/api/briefing?ids={record_id}")

    lines = _app_lines(monkeypatch, tmp_path, call)
    keys = {key for line in lines for key in line["attributes"]}
    assert any(key.startswith("legion.audit.") for key in keys), (
        "no audit line was examined"
    )
    stray = sorted(
        k
        for k in keys
        if k not in KNOWN_KEYS and not k.startswith(("legion.", "appstore."))
    )
    assert stray == []


def test_ctrl_c_and_a_clean_thread_exit_are_not_crashes(
    logging_state, monkeypatch, capsys
):
    """A stop and a thread that exits are not errors, so neither writes one."""
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    stream = _capture(monkeypatch)
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    thread = threading.Thread(target=sys.exit)
    thread.start()
    thread.join()
    assert [r for r in _lines(stream) if r["severity_number"] >= 17] == []
    assert "KeyboardInterrupt" in capsys.readouterr().err
