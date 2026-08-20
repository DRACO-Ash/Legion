"""Tests for the audit/application logging configuration.

These exist because the audit trail was silently dropped for the whole life
of the project up to 0.4.1: nothing configured logging, so the audit logger
had no handler and sat at WARNING, and every `audit_logger.info(...)` went
nowhere. The tests that were meant to cover it asserted on `caplog`, which
installs its own root handler and so passed regardless. Each test below
asserts on what a real handler actually writes to its stream.
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from src.app import _STDOUT_HANDLER_NAME, configure_logging
from src.store import APP_LOGGER_NAME, AUDIT_LOGGER_NAME, TrackedSystemsStore

SEED = [
    {
        "family_id": "log-fam",
        "family_title": "Logging Family",
        "family_sub": "sub",
        "nation": "RU",
        "designator": "LOG-1",
        "catalogue_name": "LOGSAT-1",
        "launch_year": 2021,
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
]


@pytest.fixture
def logging_state():
    """Snapshot and restore the application loggers.

    `configure_logging` mutates process-global logger state, so without this
    one test's handler or level leaks into the next.
    """
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    saved = (
        list(app_logger.handlers),
        app_logger.level,
        app_logger.propagate,
        audit_logger.level,
    )
    yield
    app_logger.handlers = saved[0]
    app_logger.setLevel(saved[1])
    app_logger.propagate = saved[2]
    audit_logger.setLevel(saved[3])


def _capture(monkeypatch, level: str | None = None) -> io.StringIO:
    """Configure logging, then redirect the installed handler at a buffer."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging.getLogger(APP_LOGGER_NAME).handlers = []
    configure_logging(level)
    handler = next(
        h
        for h in logging.getLogger(APP_LOGGER_NAME).handlers
        if h.name == _STDOUT_HANDLER_NAME
    )
    stream = io.StringIO()
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)
    return stream


def test_audit_line_reaches_the_handler(logging_state, monkeypatch):
    """The regression this whole module exists for: the line is emitted."""
    stream = _capture(monkeypatch)
    logging.getLogger(AUDIT_LOGGER_NAME).info(json.dumps({"event": "probe"}))
    assert stream.getvalue().strip() == '{"event": "probe"}'


def test_audit_line_is_bare_json_with_no_prefix(logging_state, monkeypatch):
    """A log pipeline must be able to parse the line without stripping."""
    stream = _capture(monkeypatch)
    logging.getLogger(AUDIT_LOGGER_NAME).info(
        json.dumps({"event": "system_created", "actor": "203.0.113.5"})
    )
    written = stream.getvalue().strip()
    assert json.loads(written) == {
        "event": "system_created",
        "actor": "203.0.113.5",
    }


def test_audit_line_is_written_exactly_once(logging_state, monkeypatch):
    """A handler on both the parent and the audit logger would double it."""
    stream = _capture(monkeypatch)
    logging.getLogger(AUDIT_LOGGER_NAME).info(json.dumps({"event": "probe"}))
    assert len(stream.getvalue().strip().splitlines()) == 1


def test_non_audit_records_keep_the_human_prefix(logging_state, monkeypatch):
    stream = _capture(monkeypatch)
    logging.getLogger(f"{APP_LOGGER_NAME}.store").info("store started")
    written = stream.getvalue().strip()
    assert written.endswith(f"INFO {APP_LOGGER_NAME}.store store started")
    assert not written.startswith("store started")


def test_configure_logging_is_idempotent(logging_state, monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging.getLogger(APP_LOGGER_NAME).handlers = []
    for _ in range(3):
        configure_logging()
    installed = [
        h
        for h in logging.getLogger(APP_LOGGER_NAME).handlers
        if h.name == _STDOUT_HANDLER_NAME
    ]
    assert len(installed) == 1


def test_raising_log_level_never_silences_the_audit_trail(logging_state, monkeypatch):
    """LOG_LEVEL is for diagnostics. The audit trail is a compliance record."""
    stream = _capture(monkeypatch, level="WARNING")
    logging.getLogger(f"{APP_LOGGER_NAME}.store").info("diagnostic noise")
    logging.getLogger(AUDIT_LOGGER_NAME).info(json.dumps({"event": "probe"}))
    written = stream.getvalue()
    assert "diagnostic noise" not in written
    assert json.loads(written.strip()) == {"event": "probe"}


def test_unknown_log_level_falls_back_to_info(logging_state, monkeypatch):
    stream = _capture(monkeypatch, level="NOT_A_LEVEL")
    logging.getLogger(f"{APP_LOGGER_NAME}.store").info("still visible")
    assert "still visible" in stream.getvalue()


def test_log_level_env_var_is_honoured(logging_state, monkeypatch):
    logging.getLogger(APP_LOGGER_NAME).handlers = []
    monkeypatch.setenv("LOG_LEVEL", "warning")
    configure_logging()
    assert logging.getLogger(APP_LOGGER_NAME).level == logging.WARNING


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
    # The store also emits a plain-text seeding line, which is diagnostics,
    # not audit. Audit lines are the bare-JSON ones.
    audit_lines = [
        ln
        for ln in stream.getvalue().strip().splitlines()
        if ln.strip().startswith("{")
    ]
    assert len(audit_lines) == 1
    record = json.loads(audit_lines[0])
    assert record["event"] == "system_created"
    assert record["actor"] == "203.0.113.5"
    assert record["record_id"] == created["id"]
