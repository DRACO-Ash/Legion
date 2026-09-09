from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src._version import __version__
from src.security import (
    describe_token_difference,
    enforce_rate_limit,
    extract_bearer_token,
)

NO_TOKEN_CONFIGURED_VERDICT = (
    "This deployment has no TEAM_TOKEN configured, so nothing can match. Set "
    "one in the Configuration tab and restart the app."
)

router = APIRouter()

# Strictly shorter than the platform's own probe timeout, so a stalled mount
# is converted to a value (503 with the errno) rather than hanging the probe
# and being killed silently with no diagnostic.
STORAGE_PROBE_TIMEOUT_SECONDS = 3.0


@router.get("/version")
async def version():
    return {"service": "udl-tactics-app", "version": __version__}


@router.get("/healthz")
async def healthz():
    # Liveness: dependency-free, never checks storage or UDL, so a transient
    # storage or upstream outage never restarts an otherwise-healthy container.
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request):
    """Readiness: booleans and lengths only, never a secret value. Every
    field that could answer a plausible "why won't this deploy" question is
    present at once, per observability-and-audit, rather than added one
    field per deploy cycle.
    """
    settings = request.app.state.settings
    udl_client = request.app.state.udl_client
    store = request.app.state.systems_store

    try:
        storage_writable, storage_error = await asyncio.wait_for(
            asyncio.to_thread(store.probe_writable),
            timeout=STORAGE_PROBE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        storage_writable, storage_error = False, "probe timed out"

    started_at = getattr(request.app.state, "started_at", None)
    body = {
        "status": "ok" if storage_writable else "not_ready",
        "version": __version__,
        # A token or credential changed in the platform's configuration after
        # this timestamp is not in this process. Nothing else can tell you
        # that from outside, and without it a stale worker looks identical to
        # a mistyped value.
        "started_at": started_at.isoformat() if started_at else None,
        "uptime_seconds": round((dt.datetime.now(dt.UTC) - started_at).total_seconds())
        if started_at
        else None,
        "udl_configured": udl_client.configured,
        "udl_username_len": len(settings.udl_username) if settings.udl_username else 0,
        "udl_password_len": len(settings.udl_password) if settings.udl_password else 0,
        "team_token_configured": bool(settings.team_token),
        # Characters and bytes both, because the two disagree exactly when it
        # matters. The write guard rejects on UTF-8 byte length, while len()
        # counts characters: a non-breaking space is one character and two
        # bytes, so a token carrying one reports the same team_token_len as a
        # clean one and is still refused. Publishing only characters is what
        # let that sit undiagnosed through three releases. Lengths only,
        # never the value, never a position.
        "team_token_len": len(settings.team_token) if settings.team_token else 0,
        "team_token_bytes": (
            len(settings.team_token.encode("utf-8")) if settings.team_token else 0
        ),
        "storage_writable": storage_writable,
    }
    if not storage_writable:
        # Operational detail, not a secret leak: the resolved dir and errno
        # are exactly what turns a blind redeploy-and-hope cycle into a
        # one-glance diagnosis (observability-and-audit).
        body["storage_error"] = storage_error
        return JSONResponse(status_code=503, content=body)
    return body


@router.get("/api/token-check")
async def token_check(request: Request):
    """Say how the caller's token differs from the configured one.

    Shapes and booleans only: lengths, byte counts, whether the value is
    ASCII, and which kind of difference it is. Never a character, a position
    or a digest of either value.

    Deliberately not gated by the token, because it exists for the case where
    the token is refused. It tells a caller nothing it does not already know
    about the value it just sent - a 401 from any gated route already reveals
    "this does not match" - and the strict rate limit applies so it cannot be
    driven quickly.

    This exists because a live deployment sat at "both are 43 characters" with
    nowhere to go. A look-alike hyphen from a copy through a document is one
    character and reads identically, and no length comparison can see it.
    """
    enforce_rate_limit(request.app.state.strict_limiter, request)
    configured = request.app.state.settings.team_token
    if not configured:
        return {"matches": False, "verdict": NO_TOKEN_CONFIGURED_VERDICT}
    return describe_token_difference(extract_bearer_token(request), configured)
