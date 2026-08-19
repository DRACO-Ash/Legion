"""Serves the single-file admin UI at GET /.

Still returns 200 (never a redirect), satisfying the App Store root probe,
while giving the app an actual usable surface instead of a bare JSON ping.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_UI_PATH = Path(__file__).resolve().parent.parent / "static" / "index.html"


@router.get("/", response_class=HTMLResponse)
async def root():
    return _UI_PATH.read_text(encoding="utf-8")
