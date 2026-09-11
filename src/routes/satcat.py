"""The catalogue snapshot: lookups, and what disagrees with it.

Reads only. The snapshot is a reference, not state: nothing here writes, and
nothing here corrects the catalogue. A disagreement is reported to the person
who owns the source rather than patched out of sight, because `seed_data.py`
is a verbatim mirror of a delivered spreadsheet.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.satcat import load_extract
from src.satcat_reconcile import reconcile

router = APIRouter(prefix="/api/satcat")

NOT_IN_SNAPSHOT = "That catalogue number is not in the snapshot"


@router.get("/reconciliation")
async def satcat_reconciliation(request: Request):
    """Where the catalogue and the snapshot disagree.

    A wrong catalogue number is the failure nothing else here catches: it
    plots a real satellite's element sets under another satellite's name, and
    every chart looks entirely normal.
    """
    records = request.app.state.systems_store.list(include_archived=True)
    return reconcile(records)


@router.get("/{norad_id}")
async def satcat_object(norad_id: str):
    """One row, for looking something up without leaving the application."""
    row = load_extract().get(norad_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_IN_SNAPSHOT
        )
    return row
