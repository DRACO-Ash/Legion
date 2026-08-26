"""Local development entrypoint. The container's Dockerfile runs gunicorn
directly against src.app:app; this is for `python -m src.main` on a laptop."""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    # Loopback by default: this script only ever runs on a laptop, where
    # binding every interface exposes a dev server to the local network for
    # no benefit. Set HOST explicitly to reach it from another device.
    #
    # The App Store's PORT contract (bind all interfaces so the platform's
    # ingress and probes can reach the container) is met by the Dockerfile's
    # gunicorn CMD, which is the real container entrypoint. It does not run
    # this file.
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run("src.app:app", host=host, port=port, reload=False)
