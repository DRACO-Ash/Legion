"""One CRUD surface for every list that hangs off a catalogued object.

Claims and pattern-of-life segments are the same shape: a list on the
object's compendium layer, created whole so the validators run at the
boundary, merged anti-shrink on edit, re-validated after the merge, and
archived rather than deleted.

Writing that twice would put the anti-shrink merge and the archive rule in
two places, which is two places for them to drift. It would also trip the
quality gate's duplicated-lines-on-new-code condition on its own. The store
already took this decision for the same reason: one generic collection-keyed
API rather than six near-identical sets.

So the endpoints are built once, here, and each collection is a few lines of
declaration. What varies is the field name, the path, the models and the
words in the 404.
"""

# Deliberately no `from __future__ import annotations` in this module.
# FastAPI reads the endpoint signatures at decoration time to build the
# request models, and with postponed evaluation `entry: model` is the string
# "model", which it cannot resolve to the Pydantic class held in the closure.
# Evaluating the annotations eagerly is what makes a parameterised route
# factory work at all.

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from src.security import client_key, enforce_rate_limit

SYSTEM_NOT_FOUND = "No system with that id"


def layer_or_404(request: Request, system_id: str) -> dict[str, Any]:
    """The compendium layer for a system, or a 404 naming which is missing.

    A system with no compendium layer cannot happen after the schema 2
    migration, so if it does the honest answer is that the system is unknown,
    not that the layer is.
    """
    layer = request.app.state.systems_store.compendium_object(system_id)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=SYSTEM_NOT_FOUND
        )
    return layer


def readable(exc: ValidationError) -> list[dict[str, str]]:
    """Turn a validation failure into something serialisable and readable.

    Not `exc.errors()` raw: its `ctx` carries the original exception object,
    which is not JSON serialisable, so returning it fails while serialising
    the response and the caller gets a 500 instead of the 422 that explains
    what is wrong. The message is the useful half anyway, and it is written
    for a person.
    """
    return [
        {
            "field": ".".join(str(part) for part in error["loc"]) or "entry",
            "message": error["msg"].removeprefix("Value error, "),
        }
        for error in exc.errors()
    ]


def _live(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry for entry in entries if not entry.get("archived")]


def _find(
    entries: list[dict[str, Any]], entry_id: str, not_found: str
) -> dict[str, Any]:
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)


def register_object_list(
    router: APIRouter,
    *,
    field: str,
    path: str,
    model: type[BaseModel],
    update_model: type[BaseModel],
    plural: str,
    not_found: str,
) -> None:
    """Add read, create, edit and archive for one per-object list."""

    def _write(request: Request, system_id: str, entries: list[dict[str, Any]]) -> None:
        enforce_rate_limit(request.app.state.strict_limiter, request)
        request.app.state.systems_store.update_compendium_object(
            system_id, {field: entries}, actor=client_key(request)
        )

    def _revalidated(merged: dict[str, Any]) -> dict[str, Any]:
        """Run the full rules over an edited entry.

        An update has to clear the same bar a creation does. Without this a
        PATCH could strip the citation off a FACT or the counterpart off an
        RPO segment, and the rules would be decorative: enforced once, at
        creation, and defeatable for ever afterwards.
        """
        try:
            return model.model_validate(merged).model_dump()
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=readable(exc),
            ) from exc

    @router.get(f"/objects/{{system_id}}/{path}")
    async def list_entries(
        request: Request, system_id: str, include_archived: bool = False
    ):
        entries = layer_or_404(request, system_id).get(field, [])
        shown = entries if include_archived else _live(entries)
        return {"system_id": system_id, "count": len(shown), plural: shown}

    @router.post(f"/objects/{{system_id}}/{path}", status_code=status.HTTP_201_CREATED)
    # mypy cannot follow a type held in a closure variable, which is the
    # whole point of the factory. FastAPI resolves it at decoration time.
    async def create_entry(request: Request, system_id: str, entry: model):  # type: ignore[valid-type]
        """The body is the full model, so every rule runs at the boundary
        before anything is written and the store never sees a bad entry."""
        layer = layer_or_404(request, system_id)
        stored = entry.model_dump()  # type: ignore[attr-defined]
        _write(request, system_id, [*layer.get(field, []), stored])
        return stored

    @router.patch(f"/objects/{{system_id}}/{path}/{{entry_id}}")
    async def update_entry(
        request: Request,
        system_id: str,
        entry_id: str,
        patch: update_model,  # type: ignore[valid-type]
    ):
        """Anti-shrink merge, then re-validate the whole entry."""
        layer = layer_or_404(request, system_id)
        entries = list(layer.get(field, []))
        existing = _find(entries, entry_id, not_found)

        changes = patch.model_dump(exclude_unset=True)  # type: ignore[attr-defined]
        merged = _revalidated({**existing, **changes, "id": entry_id})
        merged["archived"] = existing.get("archived", False)

        _write(
            request,
            system_id,
            [merged if e.get("id") == entry_id else e for e in entries],
        )
        return merged

    @router.delete(f"/objects/{{system_id}}/{path}/{{entry_id}}")
    async def archive_entry(request: Request, system_id: str, entry_id: str):
        """Archive, never delete. A withdrawn entry stays visible to anyone
        who asks for archived ones, so an analyst can see that something was
        asserted and later pulled rather than finding a silent gap."""
        layer = layer_or_404(request, system_id)
        entries = list(layer.get(field, []))
        existing = _find(entries, entry_id, not_found)
        archived = {**existing, "archived": True}

        _write(
            request,
            system_id,
            [archived if e.get("id") == entry_id else e for e in entries],
        )
        return archived
