from __future__ import annotations

from fastapi import APIRouter, Request

from src._version import __version__

router = APIRouter()


@router.get("/version")
async def version():
    return {"service": "udl-tactics-app", "version": __version__}


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request):
    # Exposes only a boolean about UDL configuration - never the credentials
    # themselves, never a hint about which one (username vs password) is missing.
    udl_client = request.app.state.udl_client
    return {"status": "ok", "udl_configured": udl_client.configured}
