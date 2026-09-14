"""Family assessments: the capability, context and intent synthesis.

The layer the application exists for. The catalogue holds attributes and the
timeline holds behaviour; neither can tell an analyst whether a manoeuvre
signature means inspection, servicing or attack. This does, by holding what
the class is, what it typically does, what its manoeuvre baseline is, and
what should raise concern -- every statement carrying its own provenance.

**Nothing here is authoritative because it is written down.** Every seeded
assessment loads unvalidated and the interface says so. Who is entitled to
sign one off is Ash's decision and is not encoded here: the route accepts a
name and records it, exactly like `asserted_by`, which is the whole editorial
layer in an application with no authentication.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import AfterValidator, BaseModel, ValidationError

from src.compendium_models import FamilyAssessment
from src.routes.object_lists import readable
from src.security import client_key, enforce_rate_limit
from src.store import FAMILY_ASSESSMENTS
from src.validation_policy import NAME_REQUIRED, policy, signature

router = APIRouter(prefix="/api/families")

NO_ASSESSMENT = "No assessment for that family"
WRITE_FAILED = "The assessment could not be written"


class AssessmentUpdate(BaseModel):
    """A partial edit. Every field optional, anti-shrink on merge, and the
    merged result is re-validated as a whole `FamilyAssessment` by the route,
    so an edit cannot strip the provenance off a statement."""

    one_line: dict[str, Any] | None = None
    role_summary: dict[str, Any] | None = None
    manoeuvre_baseline: str | None = None
    baseline_claim: dict[str, Any] | None = None
    what_raises_concern: list[dict[str, Any]] | None = None
    capabilities: list[dict[str, Any]] | None = None
    open_questions: list[str] | None = None


def _named(value: str) -> str:
    if not value.strip():
        raise ValueError(NAME_REQUIRED)
    return value.strip()


class Validation(BaseModel):
    """Who is signing this assessment off.

    A name, not a boolean. Ash's decision of 14 September 2026 is that any
    member of the DOK team may sign one off, and `src/validation_policy.py`
    holds that rule. With no application-level authentication the name is the
    whole of the record, so an empty one would be a validation by nobody,
    which is worse than none at all.
    """

    validated_by: Annotated[str, AfterValidator(_named)]


def _families(request: Request) -> dict[str, dict[str, Any]]:
    """Every family the catalogue holds, with its member count."""
    families: dict[str, dict[str, Any]] = {}
    for record in request.app.state.systems_store.list():
        family_id = str(record.get("family_id") or "")
        if not family_id:
            continue
        entry = families.setdefault(
            family_id,
            {
                "family_id": family_id,
                "title": record.get("family_title"),
                "sub": record.get("family_sub"),
                "nation": record.get("nation"),
                "members": 0,
            },
        )
        entry["members"] += 1
    return families


def _assessments(request: Request) -> dict[str, Any]:
    store = request.app.state.systems_store
    return {
        entry["family_id"]: entry
        for entry in store.list_compendium(FAMILY_ASSESSMENTS)
        if entry.get("family_id")
    }


def _awaiting(entry: dict[str, Any]) -> bool:
    return not str(entry.get("validated_by") or "").strip()


def _decorated(entry: dict[str, Any]) -> dict[str, Any]:
    """The stored assessment plus the flag the interface reads.

    Computed here rather than in the browser: "awaiting validation" is the
    most consequential thing on the panel, and a client-side derivation of it
    is one refactor away from silently defaulting to validated.
    """
    return {**entry, "awaiting_validation": _awaiting(entry)}


def _write(store, family_id: str, merged: dict[str, Any], actor: str) -> None:
    """Persist, and refuse to report success if nothing was written.

    The collection is keyed by `family_id`, which is the natural key and the
    reason the migration is idempotent. Passing the record's uuid matched
    nothing, the store returned None, and the route answered 200 having
    changed nothing at all: a validation that appeared to stick and did not.
    A silent no-op on a write is worse than an error.
    """
    if (
        store.update_compendium(FAMILY_ASSESSMENTS, family_id, merged, actor=actor)
        is None
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=WRITE_FAILED
        )


@router.get("/validation-policy")
async def validation_policy():
    """Who may sign an assessment off, served rather than hard-coded.

    The interface must not carry its own copy of the rule: the words an
    analyst reads before signing and the rule recorded against the signature
    have to come from one place.
    """
    return policy()


@router.get("")
async def list_families(request: Request):
    """Every family, whether it has an assessment, and whether it is signed."""
    assessments = _assessments(request)
    rows = []
    for family_id, entry in sorted(_families(request).items()):
        assessment = assessments.get(family_id)
        rows.append(
            {
                **entry,
                "has_assessment": assessment is not None,
                "awaiting_validation": assessment is None or _awaiting(assessment),
                "manoeuvre_baseline": (assessment or {}).get("manoeuvre_baseline"),
            }
        )
    return {"count": len(rows), "families": rows}


@router.get("/{family_id}/assessment")
async def family_assessment(request: Request, family_id: str):
    entry = _assessments(request).get(family_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_ASSESSMENT)
    return _decorated(entry)


@router.patch("/{family_id}/assessment")
async def update_assessment(request: Request, family_id: str, patch: AssessmentUpdate):
    """Anti-shrink merge, then re-validate the whole assessment."""
    store = request.app.state.systems_store
    enforce_rate_limit(request.app.state.strict_limiter, request)
    existing = _assessments(request).get(family_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_ASSESSMENT)
    merged = {**existing, **patch.model_dump(exclude_unset=True)}
    try:
        FamilyAssessment.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=readable(exc)
        ) from exc
    _write(store, family_id, merged, actor=client_key(request))
    return _decorated(merged)


@router.post("/{family_id}/assessment/validation")
async def validate_assessment(request: Request, family_id: str, body: Validation):
    """Record who signed this assessment off.

    Deliberately a separate route from the edit. Signing an assessment off is
    a different act from correcting a sentence in it, and folding the two
    together would let a routine edit carry a validation nobody intended.

    The entitlement is stored alongside the name, so a sign-off made today
    still states the rule it was made under if that rule later changes.
    """
    store = request.app.state.systems_store
    enforce_rate_limit(request.app.state.strict_limiter, request)
    existing = _assessments(request).get(family_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_ASSESSMENT)
    merged = {**existing, **signature(body.validated_by)}
    _write(store, family_id, merged, actor=client_key(request))
    return _decorated(merged)
