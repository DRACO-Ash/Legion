"""createApp(deps) factory equivalent for FastAPI.

build_app() wires routes, middleware, and dependencies and returns the app
without binding a socket - src/main.py does that. This keeps the app
testable in-process with a fake UDL client (testing-standards).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src._version import __version__
from src.cache import TTLCache
from src.candidate_systems import CANDIDATE_RECORDS
from src.config import Settings, load_settings
from src.family_elements import CACHE_TTL_SECONDS
from src.pol_seed import SEED_SEGMENTS
from src.routes import (
    claims,
    graph,
    health,
    satcat,
    segments,
    systems,
    udl,
    ui,
)
from src.security import RateLimiter, enforce_rate_limit
from src.seed_data import SEED_RECORDS
from src.store import (
    APP_LOGGER_NAME,
    AUDIT_LOGGER_NAME,
    TrackedSystemsStore,
)
from src.udl_client import UDLClient

logger = logging.getLogger(APP_LOGGER_NAME)

_STDOUT_HANDLER_NAME = "udl-tactics-app-stdout"


class _AuditAwareFormatter(logging.Formatter):
    """Emits an audit record as the bare JSON line it already is, so a log
    pipeline can parse it without stripping a prefix first. Everything else
    gets the usual human-readable prefix."""

    def format(self, record: logging.LogRecord) -> str:
        if record.name == AUDIT_LOGGER_NAME:
            return record.getMessage()
        return super().format(record)


def configure_logging(level: str | None = None) -> None:
    """Attach one stdout handler to the application logger.

    Without this, nothing in the process configures logging: the audit
    logger has no handler and inherits the root logger's WARNING, so every
    `audit_logger.info(...)` is discarded and the audit trail never reaches
    the container log. Verified against a real running container, not
    assumed (observability-and-audit: one structured line per privileged
    action).

    Three deliberate choices:

    - The handler sits on the parent `udl_tactics_app` logger, not on the
      audit logger, so an audit record is written exactly once. A handler on
      both would emit it twice, once per format.
    - Propagation is left on. Root has no handler under gunicorn or uvicorn,
      so propagating costs nothing, and pytest's `caplog` needs it.
    - The audit logger is pinned to INFO regardless of `LOG_LEVEL`. The
      audit trail is a compliance record, not diagnostic noise, so raising
      the level must never silence it.

    Idempotent: safe to call per worker, per test, or twice in one process.
    """
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    if not any(h.name == _STDOUT_HANDLER_NAME for h in app_logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.set_name(_STDOUT_HANDLER_NAME)
        handler.setFormatter(
            _AuditAwareFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        app_logger.addHandler(handler)

    requested = (level or os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
    resolved = logging.getLevelNamesMapping().get(requested, logging.INFO)
    app_logger.setLevel(resolved)
    logging.getLogger(AUDIT_LOGGER_NAME).setLevel(logging.INFO)


# Two-tier rate limiting: a coarse global limit protects the process; the
# finer per-route limit (applied inside routes/udl.py's _gate) protects the
# UDL-calling endpoints specifically, since those cost real UDL API calls.
GLOBAL_LIMIT_PER_MINUTE = 120
STRICT_LIMIT_PER_MINUTE = 20


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: RateLimiter):
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next):
        try:
            enforce_rate_limit(self._limiter, request)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
        return await call_next(request)


def build_app(
    settings: Settings | None = None,
    udl_client: UDLClient | None = None,
    systems_store: TrackedSystemsStore | None = None,
) -> FastAPI:
    configure_logging()
    settings = settings or load_settings()

    # Fail closed on a wildcard origin, unconditionally. This used to be
    # conditional on a team token being set; with that token gone the writes
    # are gated only by whatever sits in front of this app, so a wildcard
    # origin is strictly more dangerous than it was, not less: it would let
    # any page on the internet issue writes from a reader's browser.
    if settings.allowed_origin == "*":
        raise RuntimeError(
            "Refusing to start: ALLOWED_ORIGIN is '*'. Writes are not gated "
            "by this application, so a wildcard origin would let any origin "
            "issue them. Set an explicit ALLOWED_ORIGIN."
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.udl_client.aclose()

    app = FastAPI(title="UDL Tactics App", version=__version__, lifespan=lifespan)

    app.state.settings = settings
    # When this worker read its environment. A configuration change made after
    # this moment is not in this process: the platform has to restart it. That
    # question came up in live debugging and could not be answered from
    # outside, so /readyz reports it.
    app.state.started_at = dt.datetime.now(dt.UTC)
    app.state.udl_client = udl_client or UDLClient(
        base_url=settings.udl_base_url,
        username=settings.udl_username,
        password=settings.udl_password,
        timeout_seconds=settings.udl_timeout_seconds,
    )
    # One family chart is one UDL call per member, so an analyst clicking
    # between families would re-fetch the same element sets within seconds.
    app.state.elset_cache = TTLCache(ttl_seconds=CACHE_TTL_SECONDS)
    app.state.strict_limiter = RateLimiter(
        limit=STRICT_LIMIT_PER_MINUTE, window_seconds=60.0
    )
    global_limiter = RateLimiter(limit=GLOBAL_LIMIT_PER_MINUTE, window_seconds=60.0)
    app.state.systems_store = systems_store or TrackedSystemsStore(
        seed_records=SEED_RECORDS,
        candidate_records=CANDIDATE_RECORDS,
        pol_seeds=SEED_SEGMENTS,
    )

    allowed_origins = [settings.allowed_origin] if settings.allowed_origin else []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(GlobalRateLimitMiddleware, limiter=global_limiter)

    app.include_router(health.router)
    app.include_router(udl.router)
    app.include_router(systems.router)
    app.include_router(claims.router)
    app.include_router(segments.router)
    app.include_router(satcat.router)
    app.include_router(graph.router)
    app.include_router(ui.router)

    return app


# Module-level instance for gunicorn/uvicorn (`src.app:app`), built from real
# environment settings at import time in the container. Tests import
# build_app() directly instead, with fakes injected.
app = build_app()
