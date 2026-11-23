"""The App Store logging standard: one JSON object per line, on stdout.

The platform's Logging check (advisory now, blocking from 1 December 2026)
found three faults in 0.19.0, and all three were structural rather than
cosmetic:

● **Nothing reached stdout.** The application logged only when something was
  written to the store, and the check made ordinary requests.
● **Seven lines reached stderr.** Exactly gunicorn's and uvicorn's start-up
  messages, which never passed through the application's logging at all.
● **No line carried the request id.** Nothing logged a request.

So this module owns the format for every logger in the process, including
gunicorn's and uvicorn's, and `RequestLogMiddleware` writes one line per
request carrying the caller's `X-Request-Id`, which is then stamped on every
other line written while that request is handled.

The 0.19.2 check passed with two warnings, both about what a request carries:

● **Every line written while a request is handled needs `url.path`,
  `http.request.method` and `user_agent.original`**, besides the request id
  and the user. Only the request line had the first two, and no line had the
  third. All three are now request context, stamped like the id.
● **The request line needs `event.outcome`.** The check calls it the audit
  line for the request, and wants the path, method, status, user agent and
  outcome on it.

What a line holds, as the standard states it: `timestamp` (UTC, millisecond
precision), `severity_text`, `severity_number`, `body` and a flat
`attributes` object, with an exception carried as `exception.type`,
`exception.message` and `exception.stacktrace`. What it must never hold:
`service.name`, tenant or application ids, Authorization or Cookie values,
tokens, or query strings. The request line therefore logs the path alone, and
third-party loggers stay at WARNING: httpx logs every UDL request at INFO with
its full query string.

**INFERENCE, not FACT:** the timestamp is written as ISO 8601 with
milliseconds and a `Z` suffix. The standard's summary says "UTC,
milliseconds" and its full text was not reachable from the build
environment. If the platform wants epoch milliseconds, `_timestamp` is the
one place to change.

Standard library only, so gunicorn's master process can import it without
building the application.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
import traceback
from contextvars import ContextVar
from typing import Any

HANDLER_NAME = "udl-tactics-app-stdout"
AUDIT_LOGGER_NAME = "udl_tactics_app.audit"
REQUEST_LOGGER_NAME = "udl_tactics_app.request"

REQUEST_ID_HEADER = b"x-request-id"
USER_EMAIL_HEADER = b"x-auth-request-email"
USER_AGENT_HEADER = b"user-agent"
REQUEST_ID_ATTRIBUTE = "http.request.header.x-request-id"
USER_EMAIL_ATTRIBUTE = "user.email"
USER_AGENT_ATTRIBUTE = "user_agent.original"
METHOD_ATTRIBUTE = "http.request.method"
PATH_ATTRIBUTE = "url.path"
STATUS_ATTRIBUTE = "http.response.status_code"
OUTCOME_ATTRIBUTE = "event.outcome"

# Every line written while a request is handled carries these, whether or not
# the client sent the header: the check names the key as required, and an
# empty user agent states truthfully that none was sent. The request id and
# the user stay absent when absent, because inventing either would mislead.
REQUIRED_REQUEST_ATTRIBUTES = (PATH_ATTRIBUTE, METHOD_ATTRIBUTE, USER_AGENT_ATTRIBUTE)

# The standard's severity pairs. Python has no TRACE; anything below DEBUG
# would be one, and nothing here logs at that level.
_SEVERITY = (
    (logging.CRITICAL, "FATAL", 21),
    (logging.ERROR, "ERROR", 17),
    (logging.WARNING, "WARN", 13),
    (logging.INFO, "INFO", 9),
    (logging.DEBUG, "DEBUG", 5),
)
_TRACE = ("TRACE", 1)

# Request-scoped attributes, set by the middleware and read by the formatter,
# so a line written anywhere while a request is handled carries its id.
_request_attributes: ContextVar[dict[str, str] | None] = ContextVar(
    "request_attributes", default=None
)


def _severity(levelno: int) -> tuple[str, int]:
    for threshold, text, number in _SEVERITY:
        if levelno >= threshold:
            return text, number
    return _TRACE


def _timestamp(created: float) -> str:
    moment = dt.datetime.fromtimestamp(created, tz=dt.UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _flat(value: Any) -> Any:
    """A scalar, or a list of scalars, as an attribute value. Anything nested
    is written as its JSON text, because `attributes` must stay flat."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple) and all(
        isinstance(item, str | int | float | bool) for item in value
    ):
        return list(value)
    return json.dumps(value, default=str, sort_keys=True)


def _audit_attributes(message: str) -> dict[str, Any]:
    """An audit record's fields, each under `audit.`, so a pipeline can
    select the compliance trail without parsing the body."""
    try:
        fields = json.loads(message)
    except json.JSONDecodeError:
        return {}
    if not isinstance(fields, dict):
        return {}
    return {f"audit.{key}": _flat(value) for key, value in fields.items()}


class JsonLineFormatter(logging.Formatter):
    """Every record as one JSON object on one line, in the platform's shape."""

    def format(self, record: logging.LogRecord) -> str:
        severity_text, severity_number = _severity(record.levelno)
        message = record.getMessage()
        attributes: dict[str, Any] = {"logger.name": record.name}
        if record.name == AUDIT_LOGGER_NAME:
            attributes.update(_audit_attributes(message))
            event = attributes.get("audit.event")
            body = f"audit {event}" if event else message
        else:
            body = message
        for key, value in (getattr(record, "attributes", None) or {}).items():
            attributes[key] = _flat(value)
        attributes.update(_request_attributes.get() or {})
        if record.exc_info and record.exc_info[0] is not None:
            kind, error, trace = record.exc_info
            attributes["exception.type"] = kind.__name__
            attributes["exception.message"] = str(error)
            attributes["exception.stacktrace"] = "".join(
                traceback.format_exception(kind, error, trace)
            )
        return json.dumps(
            {
                "timestamp": _timestamp(record.created),
                "severity_text": severity_text,
                "severity_number": severity_number,
                "body": body,
                "attributes": attributes,
            },
            default=str,
        )


def _header(scope: dict[str, Any], name: bytes, limit: int = 256) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            text = value.decode("latin-1").strip()
            return "".join(ch for ch in text if ch.isprintable())[:limit] or None
    return None


def outcome(status: int) -> str:
    """`event.outcome` for a response status: a 4xx or 5xx is a failure.

    INFERENCE, not FACT: the standard names the field and not its mapping.
    `success` and `failure` are the common schema's values, and counting a
    refused request as a failure is the usual reading for an HTTP server.
    """
    return "success" if status < 400 else "failure"


def request_context(scope: dict[str, Any]) -> dict[str, str]:
    """The attributes every line written during this request carries."""
    context = {
        PATH_ATTRIBUTE: str(scope.get("path", "")),
        METHOD_ATTRIBUTE: str(scope.get("method", "")),
        USER_AGENT_ATTRIBUTE: _header(scope, USER_AGENT_HEADER, limit=512) or "",
    }
    for attribute, header in (
        (REQUEST_ID_ATTRIBUTE, REQUEST_ID_HEADER),
        (USER_EMAIL_ATTRIBUTE, USER_EMAIL_HEADER),
    ):
        value = _header(scope, header)
        if value:
            context[attribute] = value
    return context


class RequestLogMiddleware:
    """One line per HTTP request, and the request id on every line within it.

    Pure ASGI rather than `BaseHTTPMiddleware`, so the context variable is set
    in the task that runs the application. The line names the method, the path
    and the status, never the query string: a query here can carry a UDL
    filter, and the standard forbids query strings outright.

    An unhandled exception is logged here, with the request id, and answered
    with a 500. Re-raising would have uvicorn log it again after the request
    context had been reset, as a second line with no id.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self.logger = logging.getLogger(REQUEST_LOGGER_NAME)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        token = _request_attributes.set(request_context(scope))
        started = time.perf_counter()
        sent: dict[str, Any] = {"status": 500, "started": False}

        async def recording_send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                sent["status"] = message.get("status", 500)
                sent["started"] = True
            await send(message)

        try:
            await self.app(scope, receive, recording_send)
        except Exception:
            self.logger.exception("Unhandled error while handling a request")
            if sent["started"]:
                raise
            await _send_error(recording_send)
        finally:
            self._log_request(scope, sent["status"], started)
            _request_attributes.reset(token)

    def _log_request(self, scope: dict[str, Any], status: int, started: float) -> None:
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        self.logger.info(
            "%s %s %s",
            method,
            path,
            status,
            extra={
                "attributes": {
                    METHOD_ATTRIBUTE: method,
                    PATH_ATTRIBUTE: path,
                    STATUS_ATTRIBUTE: status,
                    OUTCOME_ATTRIBUTE: outcome(status),
                    "http.server.request.duration_ms": round(
                        (time.perf_counter() - started) * 1000, 1
                    ),
                }
            },
        )


async def _send_error(send: Any) -> None:
    body = b'{"detail":"Internal Server Error"}'
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def server_logconfig() -> dict[str, Any]:
    """The `logging.config.dictConfig` shape for gunicorn's `logconfig_dict`.

    One stdout handler, named so `configure_logging` recognises it in a worker
    and does not add a second. Root carries it at WARNING, so third-party
    INFO stays out; gunicorn's error logger carries it directly with
    propagation off, because the uvicorn worker copies that logger's handlers
    onto `uvicorn.error` and turns propagation off there too. Giving gunicorn
    no handler of its own would silence uvicorn's start-up and error lines
    rather than move them to stdout.
    """
    handler = {
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stdout",
        "formatter": "json",
    }
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": JsonLineFormatter}},
        "handlers": {HANDLER_NAME: handler},
        "root": {"level": "WARNING", "handlers": [HANDLER_NAME]},
        "loggers": {
            "gunicorn.error": {
                "level": "INFO",
                "handlers": [HANDLER_NAME],
                "propagate": False,
            },
            "gunicorn.access": {"level": "INFO", "handlers": [], "propagate": False},
        },
    }
