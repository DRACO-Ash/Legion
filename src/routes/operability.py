"""Search, comparison and briefing: the operability surface.

Read-only. Everything here assembles what the store already holds into the
shape an analyst working at speed needs: find a thing without knowing where
it lives, put two to four of them side by side, and produce the write-up.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from src.briefing import build_briefing
from src.comparison import (
    MAX_SUBJECTS,
    MIN_SUBJECTS,
    build_comparison,
)
from src.comparison import (
    _family_subject as family_subject,
)
from src.comparison import (
    _object_subject as object_subject,
)
from src.graph import FAMILY_PREFIX
from src.store import FAMILY_ASSESSMENTS

router = APIRouter(prefix="/api")

WRONG_COUNT = (
    f"Compare between {MIN_SUBJECTS} and {MAX_SUBJECTS} subjects. One is not "
    "a comparison, and past four the columns are too narrow to read."
)
UNKNOWN_SUBJECT = "No object or family with that id"
SEARCH_LIMIT = 12
SPACE = " "
SEPARATOR = " · "
# A module-level singleton: FastAPI needs the Query object, and evaluating it
# in the signature is a mutable default in all but name (ruff B008).
IDS_QUERY = Query(default=[])


def _assessments(request: Request) -> dict[str, Any]:
    return {
        entry["family_id"]: entry
        for entry in request.app.state.systems_store.list_compendium(FAMILY_ASSESSMENTS)
        if entry.get("family_id")
    }


def _subject(request: Request, subject_id: str) -> dict[str, Any] | None:
    store = request.app.state.systems_store
    records = store.list()
    assessments = _assessments(request)
    if subject_id.startswith(FAMILY_PREFIX):
        family_id = subject_id[len(FAMILY_PREFIX) :]
        members = [r for r in records if str(r.get("family_id")) == family_id]
        if not members:
            return None
        return family_subject(family_id, members, assessments.get(family_id))
    record = next((r for r in records if r["id"] == subject_id), None)
    if record is None:
        return None
    layer = store.compendium_object(subject_id) or {}
    return object_subject(record, layer, assessments.get(str(record.get("family_id"))))


def _matches(needle: str, haystack: str) -> bool:
    return needle in haystack.lower()


def _object_rows(records: list[dict[str, Any]], needle: str) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        fields = SPACE.join(
            str(record.get(field) or "")
            for field in ("catalogue_name", "designator", "norad_id", "notes")
        )
        if not needle or _matches(needle, fields):
            rows.append(
                {
                    "id": record["id"],
                    "kind": "object",
                    "label": record.get("catalogue_name"),
                    "detail": SEPARATOR.join(
                        [
                            str(record.get("nation")),
                            str(record.get("regime")),
                            str(record.get("norad_id") or "no NORAD id"),
                        ]
                    ),
                }
            )
    return rows


def _family_rows(records: list[dict[str, Any]], needle: str) -> list[dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    for record in records:
        family_id = str(record.get("family_id") or "")
        if family_id and family_id not in families:
            families[family_id] = {
                "id": FAMILY_PREFIX + family_id,
                "kind": "family",
                "label": record.get("family_title"),
                "detail": str(record.get("family_sub") or ""),
                "haystack": f"{family_id} {record.get('family_title')} "
                f"{record.get('family_sub')}",
            }
    rows = []
    for entry in families.values():
        haystack = entry.pop("haystack")
        if not needle or _matches(needle, haystack):
            rows.append(entry)
    return rows


@router.get("/search")
async def search(request: Request, q: str = Query(default="", max_length=120)):
    """Everything an analyst might jump to, ranked plainly.

    Deliberately a substring match rather than a fuzzy score. A palette that
    reorders on its own is one an analyst cannot learn, and at this catalogue
    size there is nothing to gain from cleverness. Families sort first,
    because jumping to a class is the coarser and commoner move.
    """
    needle = q.strip().lower()
    records = request.app.state.systems_store.list()
    results = _object_rows(records, needle) + _family_rows(records, needle)
    results.sort(key=lambda row: (row["kind"] != "family", str(row["label"]).lower()))
    return {"query": q, "count": len(results), "results": results[:SEARCH_LIMIT]}


def _subjects_or_400(request: Request, ids: list[str]) -> list[dict[str, Any]]:
    if not MIN_SUBJECTS <= len(ids) <= MAX_SUBJECTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=WRONG_COUNT)
    subjects = []
    for subject_id in ids:
        subject = _subject(request, subject_id)
        if subject is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{UNKNOWN_SUBJECT}: {subject_id}",
            )
        subjects.append(subject)
    return subjects


@router.get("/compare")
async def compare(request: Request, ids: list[str] = IDS_QUERY):
    """Two to four objects or families, side by side."""
    return build_comparison(_subjects_or_400(request, ids))


@router.get("/briefing")
async def briefing(request: Request, ids: list[str] = IDS_QUERY):
    """The paste-ready write-up, in house style, provenance carried.

    One subject is allowed here although a comparison needs two: briefing a
    single object is the commoner task, and refusing it would send an analyst
    to copy the panel by hand, which is how provenance gets lost.
    """
    subjects = []
    for subject_id in ids[:MAX_SUBJECTS]:
        subject = _subject(request, subject_id)
        if subject is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{UNKNOWN_SUBJECT}: {subject_id}",
            )
        subjects.append(subject)
    if not subjects:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=WRONG_COUNT)
    return build_briefing(build_comparison(subjects))
