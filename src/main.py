"""Local development entrypoint. The container's Dockerfile runs gunicorn
directly against src.app:app; this is for `python -m src.main` on a laptop."""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("src.app:app", host="0.0.0.0", port=port, reload=False)
