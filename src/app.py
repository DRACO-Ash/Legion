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
from src.assessment_seed import SEED_ASSESSMENTS
from src.cache import TTLCache
from src.candidate_systems import CANDIDATE_RECORDS
from src.config import Settings, load_settings
from src.family_elements import CACHE_TTL_SECONDS
from src.logging_standard import HANDLER_NAME, JsonLineFormatter, RequestLogMiddleware
from src.pol_seed import SEED_SEGMENTS
from src.routes import (
    claims,
    families,
    graph,
    health,
    operability,
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

_STDOUT_HANDLER_NAME = HANDLER_NAME


def configure_logging(level: str | None = None) -> None:
    """One JSON-lines handler on stdout, for every logger in the process.

    History worth keeping. Until 0.4.2 nothing configured logging, so the
    audit logger had no handler and every audit line was discarded; the tests
    that should have caught it asserted through `caplog`, which installs its
    own handler. Until 0.19.1 the handler sat on the application logger and
    wrote a human-readable prefix, so gunicorn's and uvicorn's lines went to
    stderr untouched and an ordinary request wrote nothing at all. The
    platform's Logging check found both. `src/logging_standard.py` has the
    format and the reasons.

    Four deliberate choices:

    - The handler sits on the root logger, so every logger in the process,
      the application's, the server's and the standard library's warnings,
      writes the same shape to the same stream.
    - Root stays at WARNING. httpx logs each UDL request at INFO with its full
      query string, and the standard forbids query strings.
    - The application logger takes `LOG_LEVEL` and propagates to root, so a
      record is written exactly once, and `caplog` still sees it.
    - The audit logger is pinned to INFO regardless of `LOG_LEVEL`. The audit
      trail is a compliance record, so raising the level must never silence
      it.

    Under gunicorn, `src/gunicorn_conf.py` installs the same handler, by the
    same name, before any worker starts, and this function recognises it
    rather than adding a second. Idempotent: safe per worker, per test, or
    twice in one process.
    """
    root = logging.getLogger()
    if not any(h.name == _STDOUT_HANDLER_NAME for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.set_name(_STDOUT_HANDLER_NAME)
        handler.setFormatter(JsonLineFormatter())
        root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.captureWarnings(True)

    requested = (level or os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
    resolved = logging.getLevelNamesMapping().get(requested, logging.INFO)
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.setLevel(resolved)
    app_logger.propagate = True
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
        assessment_seeds=SEED_ASSESSMENTS,
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
    # Outermost, so a request refused by the rate limiter is logged as well.
    app.add_middleware(RequestLogMiddleware)

    app.include_router(health.router)
    app.include_router(udl.router)
    app.include_router(systems.router)
    app.include_router(claims.router)
    app.include_router(segments.router)
    app.include_router(satcat.router)
    app.include_router(graph.router)
    app.include_router(families.router)
    app.include_router(operability.router)
    app.include_router(ui.router)

    return app


# Module-level instance for gunicorn/uvicorn (`src.app:app`), built from real
# environment settings at import time in the container. Tests import
# build_app() directly instead, with fakes injected.
app = build_app()
