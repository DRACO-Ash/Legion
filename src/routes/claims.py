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

The four endpoints themselves come from `object_lists.register_object_list`,
which pattern-of-life segments also use. The rules that matter -- validate at
the boundary, anti-shrink merge, re-validate after the merge, archive rather
than delete -- live there in one copy.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.compendium_models import Claim, ClaimUpdate
from src.provenance import legend
from src.routes.object_lists import register_object_list

router = APIRouter(prefix="/api")

CLAIM_NOT_FOUND = "No claim with that id on this system"


@router.get("/provenance/legend")
async def provenance_legend():
    """What the markers, confidence levels and source classes mean.

    Served rather than hard-coded in the interface so the words an analyst
    reads cannot drift from the rules the validators enforce.
    """
    return legend()


register_object_list(
    router,
    field="claims",
    path="claims",
    model=Claim,
    update_model=ClaimUpdate,
    plural="claims",
    not_found=CLAIM_NOT_FOUND,
)
