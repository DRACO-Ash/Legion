"""Local development entrypoint. The container's Dockerfile runs gunicorn
directly against src.app:app; this is for `python -m src.main` on a laptop."""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    # Binding 0.0.0.0 is required by the App Store's PORT contract (the
    # deployed container must be reachable on all interfaces for the
    # platform's own ingress/probe). This file only runs on a laptop for
    # local dev; the actual container entrypoint is gunicorn, invoked
    # directly from the Dockerfile CMD, not this script.
    uvicorn.run("src.app:app", host="0.0.0.0", port=port, reload=False)  # nosec B104
