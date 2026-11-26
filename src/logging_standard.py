"""The App Store logging standard: one JSON object per line, on stdout.

Every rule here is FACT, read from the App Store's own "Logging requirements"
page (`pipeline/logging`, read 27 November 2026 through the App Store MCP
server). Until then this module was built from the check's findings alone and
two of its choices were marked INFERENCE: both turned out right, and five
other things turned out wrong. The page also says the check is advisory until
**Monday 7 December 2026** and blocks from then.

A line holds `timestamp` (RFC 3339, UTC, milliseconds, `Z`), `severity_text`,
`severity_number`, `body` and a flat `attributes` object, and nothing else at
the top level. The rules this module enforces, each in the page's words:

● **A missing header leaves its attribute out.** "Do not write `null`, an
  empty string or an empty array." 0.19.3 wrote an empty user agent; that was
  wrong.
● **The request id is an array**: `http.request.header.x-request-id` is
  `["<id>"]`.
● **Every line written while a request is handled** carries the request id,
  `user.email`, `url.path`, `http.request.method` and `user_agent.original`,
  each when present.
● **One request line when each request completes**, adding
  `http.response.status_code`, `event.outcome` (`success` below 400,
  `failure` from 400, `unknown` when the client went away first) and
  `http.route` when a route matched. Never `client.address`: the platform
  passes no trusted one.
● **An unknown method is `_OTHER`**, with the method as sent in
  `http.request.method_original`.
● **A key OpenTelemetry does not define starts with the app's name** and is
  never invented inside an OpenTelemetry namespace. Legion's own keys are
  `legion.*`: `legion.audit.*`, `legion.logger.name`,
  `legion.request.duration_ms`.
● **Values are bounded**: body 2,000 characters, exception message 1,000,
  stack trace 4,000 (both ends kept), any other string 256, an array 4 items.
  A cut is marked `[truncated]` and sets `appstore.log.truncated`.
● **Uncaught errors are contract lines**, never a traceback on stderr.
● **Security events** are their own lines with `otel.event.name`,
  `event.outcome` and `code.function.name`. Legion handles two:
  `appstore.app.start` and `appstore.app.stop`, and `appstore.data.export`
  for a briefing, a report that leaves the application.

Never logged: Authorization or Cookie values, tokens, query strings, request
or response bodies, or any personal data beyond `user.email`. Third-party
loggers stay at WARNING because httpx logs each UDL request at INFO with its
full query string.

Standard library only, so gunicorn's master process can import it without
building the application.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
import threading
import time
import traceback
from contextvars import ContextVar
from typing import Any

HANDLER_NAME = "udl-tactics-app-stdout"
AUDIT_LOGGER_NAME = "udl_tactics_app.audit"
REQUEST_LOGGER_NAME = "udl_tactics_app.request"
SECURITY_LOGGER_NAME = "udl_tactics_app.security"
APP_PREFIX = "legion"

REQUEST_ID_HEADER = b"x-request-id"
USER_EMAIL_HEADER = b"x-auth-request-email"
USER_AGENT_HEADER = b"user-agent"
REQUEST_ID_ATTRIBUTE = "http.request.header.x-request-id"
USER_EMAIL_ATTRIBUTE = "user.email"
USER_AGENT_ATTRIBUTE = "user_agent.original"
METHOD_ATTRIBUTE = "http.request.method"
METHOD_ORIGINAL_ATTRIBUTE = "http.request.method_original"
PATH_ATTRIBUTE = "url.path"
ROUTE_ATTRIBUTE = "http.route"
STATUS_ATTRIBUTE = "http.response.status_code"
OUTCOME_ATTRIBUTE = "event.outcome"
EVENT_NAME_ATTRIBUTE = "otel.event.name"
FUNCTION_ATTRIBUTE = "code.function.name"
TRUNCATED_ATTRIBUTE = "appstore.log.truncated"
LOGGER_ATTRIBUTE = f"{APP_PREFIX}.logger.name"
DURATION_ATTRIBUTE = f"{APP_PREFIX}.request.duration_ms"
AUDIT_PREFIX = f"{APP_PREFIX}.audit."

# The standard's value limits, in characters.
MAX_BODY = 2000
MAX_EXCEPTION_MESSAGE = 1000
MAX_STACKTRACE = 4000
MAX_ATTRIBUTE = 256
MAX_LIST_ITEMS = 4
TRUNCATION_MARK = "[truncated]"

# OpenTelemetry's known HTTP methods. Any other is logged as _OTHER.
HTTP_METHODS = frozenset(
    {
        "GET",
        "HEAD",
        "POST",
        "PUT",
        "DELETE",
        "CONNECT",
        "OPTIONS",
        "TRACE",
        "PATCH",
        "QUERY",
    }
)

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
# so a line written anywhere while a request is handled carries them.
_request_attributes: ContextVar[dict[str, Any] | None] = ContextVar(
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


def _cut(value: str, attributes: dict[str, Any], limit: int) -> str:
    if len(value) <= limit:
        return value
    attributes[TRUNCATED_ATTRIBUTE] = True
    return value[:limit] + TRUNCATION_MARK


def _cut_middle(value: str, attributes: dict[str, Any]) -> str:
    """Both ends of a stack trace: Python puts the exception at the end."""
    if len(value) <= MAX_STACKTRACE:
        return value
    attributes[TRUNCATED_ATTRIBUTE] = True
    half = MAX_STACKTRACE // 2
    return value[:half] + "\n" + TRUNCATION_MARK + "\n" + value[-half:]


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


def _bounded(attributes: dict[str, Any]) -> dict[str, Any]:
    """Every string cut to 256 characters and every list to four items."""
    out: dict[str, Any] = {}
    for key, raw in attributes.items():
        value = _flat(raw)
        if isinstance(value, list):
            if len(value) > MAX_LIST_ITEMS:
                out[TRUNCATED_ATTRIBUTE] = True
            value = [
                _cut(item, out, MAX_ATTRIBUTE) if isinstance(item, str) else item
                for item in value[:MAX_LIST_ITEMS]
            ]
        elif isinstance(value, str):
            value = _cut(value, out, MAX_ATTRIBUTE)
        out[key] = value
    return out


def _type_name(kind: type) -> str:
    """Fully qualified, such as json.decoder.JSONDecodeError."""
    if kind.__module__ == "builtins":
        return kind.__qualname__
    return f"{kind.__module__}.{kind.__qualname__}"


def _audit_attributes(message: str) -> dict[str, Any]:
    """An audit record's fields under `legion.audit.`, so a pipeline can
    select the trail without parsing the body."""
    try:
        fields = json.loads(message)
    except json.JSONDecodeError:
        return {}
    if not isinstance(fields, dict):
        return {}
    return {AUDIT_PREFIX + key: value for key, value in fields.items()}


class JsonLineFormatter(logging.Formatter):
    """Every record as one JSON object on one line, in the platform's shape."""

    def format(self, record: logging.LogRecord) -> str:
        severity_text, severity_number = _severity(record.levelno)
        message = record.getMessage()
        raw: dict[str, Any] = {LOGGER_ATTRIBUTE: record.name}
        if record.name == AUDIT_LOGGER_NAME:
            raw.update(_audit_attributes(message))
            event = raw.get(AUDIT_PREFIX + "event")
            body = f"audit {event}" if event else message
        else:
            body = message
        raw.update(getattr(record, "attributes", None) or {})
        raw.update(_request_attributes.get() or {})
        attributes = _bounded(raw)
        if record.exc_info and record.exc_info[0] is not None:
            kind, error, trace = record.exc_info
            attributes["exception.type"] = _type_name(kind)
            attributes["exception.message"] = _cut(
                str(error), attributes, MAX_EXCEPTION_MESSAGE
            )
            attributes["exception.stacktrace"] = _cut_middle(
                "".join(traceback.format_exception(kind, error, trace)), attributes
            )
        body = _cut(body, attributes, MAX_BODY)
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


def security_event(
    name: str,
    function: str,
    body: str,
    *,
    success: bool = True,
    extra: dict[str, Any] | None = None,
) -> None:
    """One security event line: INFO for a success, WARN for a failure."""
    logging.getLogger(SECURITY_LOGGER_NAME).log(
        logging.INFO if success else logging.WARNING,
        body,
        extra={
            "attributes": {
                EVENT_NAME_ATTRIBUTE: name,
                OUTCOME_ATTRIBUTE: "success" if success else "failure",
                FUNCTION_ATTRIBUTE: function,
                **(extra or {}),
            }
        },
    )


def _log_uncaught(kind: type[BaseException], error: BaseException, trace: Any) -> None:
    """An uncaught exception stops the process: a FATAL contract line, not a
    plain-text traceback on stderr. Ctrl-C is a stop, not a crash."""
    if issubclass(kind, KeyboardInterrupt):
        sys.__excepthook__(kind, error, trace)
        return
    logging.getLogger(APP_PREFIX).critical(
        "uncaught exception", exc_info=(kind, error, trace)
    )


def _log_thread_crash(args: threading.ExceptHookArgs) -> None:
    """A crashed thread is an ERROR line. A thread that exits did not crash."""
    if issubclass(args.exc_type, SystemExit) or args.exc_value is None:
        return
    exc_info = (args.exc_type, args.exc_value, args.exc_traceback)
    logging.getLogger(APP_PREFIX).error(
        "uncaught exception in a thread", exc_info=exc_info
    )


def install_exception_hooks() -> None:
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_thread_crash


def _header(scope: dict[str, Any], name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            text = value.decode("latin-1").strip()
            return "".join(ch for ch in text if ch.isprintable()) or None
    return None


def outcome(status: int) -> str:
    """`event.outcome` for a completed response, as the standard defines it."""
    return "success" if status < 400 else "failure"


def method_attributes(method: str) -> dict[str, str]:
    if method in HTTP_METHODS:
        return {METHOD_ATTRIBUTE: method}
    return {METHOD_ATTRIBUTE: "_OTHER", METHOD_ORIGINAL_ATTRIBUTE: method}


def request_context(scope: dict[str, Any]) -> dict[str, Any]:
    """What every line written during this request carries. A header the
    client did not send leaves its attribute out."""
    context: dict[str, Any] = {
        PATH_ATTRIBUTE: str(scope.get("path", "")),
        **method_attributes(str(scope.get("method", ""))),
    }
    request_id = _header(scope, REQUEST_ID_HEADER)
    if request_id:
        context[REQUEST_ID_ATTRIBUTE] = [request_id]
    for attribute, header in (
        (USER_EMAIL_ATTRIBUTE, USER_EMAIL_HEADER),
        (USER_AGENT_ATTRIBUTE, USER_AGENT_HEADER),
    ):
        value = _header(scope, header)
        if value:
            context[attribute] = value
    return context


class RequestLogMiddleware:
    """One request line per HTTP request, and the request's attributes on
    every line written while it is handled.

    Pure ASGI rather than `BaseHTTPMiddleware`, so the context variable is set
    in the task that runs the application. The router writes the matched route
    into the shared scope, which is where `http.route` comes from; a request
    no route matched, such as a 404, carries none.

    An unhandled exception is logged here, with the request's attributes, and
    answered with a 500. Re-raising would have uvicorn log it again after the
    context had been reset. A response that started and never finished, such
    as when the client went away, has outcome `unknown`.
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
        sent: dict[str, Any] = {"status": 500, "started": False, "finished": False}

        async def recording_send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                sent["status"] = message.get("status", 500)
                sent["started"] = True
            await send(message)
            if message.get("type") == "http.response.body" and not message.get(
                "more_body"
            ):
                sent["finished"] = True

        try:
            await self.app(scope, receive, recording_send)
        except Exception:
            self.logger.exception("Unhandled error while handling a request")
            if sent["started"]:
                raise
            await _send_error(recording_send)
        finally:
            self._log_request(scope, sent, started)
            _request_attributes.reset(token)

    def _log_request(
        self, scope: dict[str, Any], sent: dict[str, Any], started: float
    ) -> None:
        status = sent["status"]
        attributes: dict[str, Any] = {
            STATUS_ATTRIBUTE: status,
            OUTCOME_ATTRIBUTE: outcome(status) if sent["finished"] else "unknown",
            DURATION_ATTRIBUTE: round((time.perf_counter() - started) * 1000, 1),
        }
        route = getattr(scope.get("route"), "path", None)
        if isinstance(route, str) and route.startswith("/"):
            attributes[ROUTE_ATTRIBUTE] = route
        self.logger.info(
            "%s %s %s",
            scope.get("method", ""),
            scope.get("path", ""),
            status,
            extra={"attributes": attributes},
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
    rather than move them to stdout. The access log is silenced: its lines
    hold the query string, and the request line replaces it.
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
