"""Single source of truth for the running app's version.

Read from src/VERSION at import time, not hardcoded here, so the FastAPI
app metadata, the /version endpoint, and the packaged file can never
disagree - the file ships inside the Docker image (COPY src ./src already
includes it), and scripts/bump_version.sh is the only thing that edits it.

Per packaging's version-normalisation rule: whatever version string is
entered in the App Store submission's "App Details" step must match this
file's contents at the time of that submission - the bump script's git tag
is the reference point to check against before submitting.
"""

from __future__ import annotations

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent / "VERSION"

try:
    __version__ = _VERSION_FILE.read_text(encoding="utf-8").strip()
except FileNotFoundError:
    __version__ = "0.0.0-unknown"
