"""CRUD for the tracked-systems catalogue.

Reads (list, get) are public - low-cost, no upstream call, no reason to
gate per security-hardening's "reads of public data may be open". Writes
(create, update, archive) are state-changing and gated by the team token
and the strict rate-limit tier, same as the UDL routes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from src.models import TrackedSystem, TrackedSystemCreate, TrackedSystemList, TrackedSystemUpdate
from src.security import enforce_rate_limit, enforce_team_token

router = APIRouter(prefix="/api/systems")


def _gate_write(request: Request) -> None:
    settings = request.app.state.settings
    enforce_rate_limit(request.app.state.strict_limiter, request)
    enforce_team_token(request, settings.team_token)


@router.get("", response_model=TrackedSystemList)
async def list_systems(
    request: Request,
    nation: str | None = None,
    regime: str | None = None,
    status_filter: str | None = None,
    q: str | None = None,
    include_archived: bool = False,
):
    store = request.app.state.systems_store
    records = store.list(
        nation=nation, regime=regime, status=status_filter, q=q, include_archived=include_archived
    )
    return TrackedSystemList(count=len(records), systems=records)


@router.get("/{system_id}", response_model=TrackedSystem)
async def get_system(request: Request, system_id: str):
    store = request.app.state.systems_store
    record = store.get(system_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No system with that id")
    return record


@router.post("", response_model=TrackedSystem, status_code=status.HTTP_201_CREATED)
async def create_system(request: Request, payload: TrackedSystemCreate):
    _gate_write(request)
    store = request.app.state.systems_store
    return store.create(payload.model_dump())


@router.patch("/{system_id}", response_model=TrackedSystem)
async def update_system(request: Request, system_id: str, payload: TrackedSystemUpdate):
    _gate_write(request)
    store = request.app.state.systems_store
    updated = store.update(system_id, payload.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No system with that id")
    return updated


@router.delete("/{system_id}", response_model=TrackedSystem)
async def archive_system(request: Request, system_id: str):
    """Archives rather than deletes, per data-layer: a lifecycle-ended
    record stays auditable instead of vanishing."""
    _gate_write(request)
    store = request.app.state.systems_store
    archived = store.archive(system_id)
    if archived is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No system with that id")
    return archived
