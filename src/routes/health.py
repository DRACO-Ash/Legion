from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src._version import __version__
from src.classification import CLASSIFICATION, CLASSIFICATION_BANNER, HANDLING

router = APIRouter()

# Strictly shorter than the platform's own probe timeout, so a stalled mount
# is converted to a value (503 with the errno) rather than hanging the probe
# and being killed silently with no diagnostic.
STORAGE_PROBE_TIMEOUT_SECONDS = 3.0


@router.get("/version")
async def version():
    """Service identity, and the classification posture it operates under.

    The marking is served rather than hard-coded in the interface so one
    string cannot drift from another: the banner the analyst reads and the
    rule the `Claim` validator enforces come from the same module.
    """
    return {
        "service": "udl-tactics-app",
        "version": __version__,
        "classification": CLASSIFICATION,
        "handling": HANDLING,
        "classification_banner": CLASSIFICATION_BANNER,
    }


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
        "storage_writable": storage_writable,
    }
    if not storage_writable:
        # Operational detail, not a secret leak: the resolved dir and errno
        # are exactly what turns a blind redeploy-and-hope cycle into a
        # one-glance diagnosis (observability-and-audit).
        body["storage_error"] = storage_error
        return JSONResponse(status_code=503, content=body)
    return body
