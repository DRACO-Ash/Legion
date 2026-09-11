"""Claims attached to a catalogued object, and the legend that explains them.

Scope note, stated rather than left implicit. The build specification asks for
claims "attached to any object or family". This phase does objects. Family
level claims are modelled by `FamilyAssessment`, which is a Phase 5
deliverable with its own required fields and its own validation gate, and
inventing a parallel family-claim store now would mean migrating it away
later. So the family routes arrive with the assessment that owns them.

Reads are open, as everything here is: there is no application-level
authentication and that was a decision. Writes go through the strict rate
limiter, which is what protects against runaway or accidental volume.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from src.compendium_models import Claim, ClaimUpdate
from src.provenance import legend
from src.security import client_key, enforce_rate_limit

router = APIRouter(prefix="/api")

SYSTEM_NOT_FOUND = "No system with that id"
CLAIM_NOT_FOUND = "No claim with that id on this system"
CLAIMS_FIELD = "claims"


def _gate_write(request: Request) -> None:
    enforce_rate_limit(request.app.state.strict_limiter, request)


def _layer_or_404(request: Request, system_id: str) -> dict[str, Any]:
    """The compendium layer for a system, or a 404 naming which is missing.

    A system with no compendium layer cannot happen after the schema 2
    migration, so if it does the honest answer is that the system is unknown,
    not that the layer is.
    """
    store = request.app.state.systems_store
    layer = store.compendium_object(system_id)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=SYSTEM_NOT_FOUND
        )
    return layer


def _live(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [claim for claim in claims if not claim.get("archived")]


def _find(claims: list[dict[str, Any]], claim_id: str) -> dict[str, Any]:
    for claim in claims:
        if claim.get("id") == claim_id:
            return claim
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CLAIM_NOT_FOUND)


def _revalidated(merged: dict[str, Any]) -> dict[str, Any]:
    """Run the full provenance rules over an edited claim.

    An update has to clear the same bar a creation does. Without this a PATCH
    could strip the citation off a FACT or the owner off a TBC, and the rules
    would be decorative: enforced once, at creation, and defeatable for ever
    afterwards.
    """
    try:
        return Claim.model_validate(merged).model_dump()
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_readable(exc),
        ) from exc


def _readable(exc: ValidationError) -> list[dict[str, str]]:
    """Turn a validation failure into something serialisable and readable.

    Not `exc.errors()` raw: its `ctx` carries the original exception object,
    which is not JSON serialisable, so returning it fails while serialising
    the response and the caller gets a 500 instead of the 422 that explains
    what is wrong. The message is the useful half anyway, and it is written
    for a person.
    """
    return [
        {
            "field": ".".join(str(part) for part in error["loc"]) or "claim",
            "message": error["msg"].removeprefix("Value error, "),
        }
        for error in exc.errors()
    ]


@router.get("/provenance/legend")
async def provenance_legend():
    """What the markers, confidence levels and source classes mean.

    Served rather than hard-coded in the interface so the words an analyst
    reads cannot drift from the rules the validators enforce.
    """
    return legend()


@router.get("/objects/{system_id}/claims")
async def list_claims(request: Request, system_id: str, include_archived: bool = False):
    layer = _layer_or_404(request, system_id)
    claims = layer.get(CLAIMS_FIELD, [])
    shown = claims if include_archived else _live(claims)
    return {"system_id": system_id, "count": len(shown), "claims": shown}


@router.post("/objects/{system_id}/claims", status_code=status.HTTP_201_CREATED)
async def create_claim(request: Request, system_id: str, claim: Claim):
    """Store one claim against an object.

    The body is a full `Claim`, so every provenance rule runs at the boundary
    before anything is written: FastAPI rejects an unsourced FACT, an
    ownerless TBC or an internal assessment with no public basis with a 422,
    and the store never sees it.
    """
    _gate_write(request)
    layer = _layer_or_404(request, system_id)
    stored = claim.model_dump()
    claims = [*layer.get(CLAIMS_FIELD, []), stored]
    request.app.state.systems_store.update_compendium_object(
        system_id, {CLAIMS_FIELD: claims}, actor=client_key(request)
    )
    return stored


@router.patch("/objects/{system_id}/claims/{claim_id}")
async def update_claim(
    request: Request, system_id: str, claim_id: str, patch: ClaimUpdate
):
    """Anti-shrink merge, then re-validate the whole claim."""
    _gate_write(request)
    layer = _layer_or_404(request, system_id)
    claims = list(layer.get(CLAIMS_FIELD, []))
    existing = _find(claims, claim_id)

    changes = patch.model_dump(exclude_unset=True)
    merged = _revalidated({**existing, **changes, "id": claim_id})
    merged["archived"] = existing.get("archived", False)

    updated = [merged if entry.get("id") == claim_id else entry for entry in claims]
    request.app.state.systems_store.update_compendium_object(
        system_id, {CLAIMS_FIELD: updated}, actor=client_key(request)
    )
    return merged


@router.delete("/objects/{system_id}/claims/{claim_id}")
async def archive_claim(request: Request, system_id: str, claim_id: str):
    """Archive, never delete. A withdrawn claim stays visible to anyone who
    asks for archived ones, so an analyst can see that an assessment was made
    and later pulled rather than finding a silent gap."""
    _gate_write(request)
    layer = _layer_or_404(request, system_id)
    claims = list(layer.get(CLAIMS_FIELD, []))
    existing = _find(claims, claim_id)
    archived = {**existing, "archived": True}

    updated = [archived if entry.get("id") == claim_id else entry for entry in claims]
    request.app.state.systems_store.update_compendium_object(
        system_id, {CLAIMS_FIELD: updated}, actor=client_key(request)
    )
    return archived
