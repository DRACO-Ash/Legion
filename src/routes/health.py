from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src._version import __version__

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

    body = {
        "status": "ok" if storage_writable else "not_ready",
        "version": __version__,
        "udl_configured": udl_client.configured,
        "udl_username_len": len(settings.udl_username) if settings.udl_username else 0,
        "udl_password_len": len(settings.udl_password) if settings.udl_password else 0,
        "team_token_configured": bool(settings.team_token),
        "team_token_len": len(settings.team_token) if settings.team_token else 0,
        "storage_writable": storage_writable,
    }
    if not storage_writable:
        # Operational detail, not a secret leak: the resolved dir and errno
        # are exactly what turns a blind redeploy-and-hope cycle into a
        # one-glance diagnosis (observability-and-audit).
        body["storage_error"] = storage_error
        return JSONResponse(status_code=503, content=body)
    return body
