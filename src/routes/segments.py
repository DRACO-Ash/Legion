"""Pattern-of-life segments on a catalogued object, and the mode vocabulary.

The assessed behavioural history. Kept deliberately distinct from the live
element-set charts, which are the raw observed data from UDL: the timeline
says what the behaviour has been assessed to mean, the chart says what the
data shows, and an assessment is never drawn as if it were telemetry.

The four endpoints come from `object_lists.register_object_list`, the same
factory the claims routes use, so the anti-shrink merge, the re-validation
after it and the archive-not-delete rule exist in one copy.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.compendium_models import PatternOfLifeSegment, PatternOfLifeSegmentUpdate
from src.pol import build_timeline, modes
from src.routes.object_lists import layer_or_404, register_object_list

router = APIRouter(prefix="/api")

SEGMENT_NOT_FOUND = "No segment with that id on this system"


@router.get("/pol/modes")
async def pol_modes():
    """What each behavioural mode means, and how it is drawn.

    Served rather than hard-coded so the words an analyst reads cannot drift
    from the vocabulary the validators enforce, and so the interface cannot
    invent a duration for a mode the model calls instantaneous.
    """
    return modes()


@router.get("/objects/{system_id}/timeline")
async def object_timeline(request: Request, system_id: str):
    """The object's assessed history, placed on a time axis and sorted.

    A read-side assembler rather than work the interface does. The epoch
    precision rule lives in `parse_pol_epoch`, and a second copy of it in
    JavaScript would drift: a month-precision band would end up drawn as if
    someone had observed a day. The browser gets positions and a stated
    precision, and owns only how a band and a node are drawn.

    An ongoing segment has no end, so it is placed at the axis end and says
    so. Giving it a made-up finish would read as a behaviour that stopped.
    """
    layer = layer_or_404(request, system_id)
    live = [s for s in layer.get("pol_segments", []) if not s.get("archived")]
    store = request.app.state.systems_store
    names = {
        record["id"]: record.get("catalogue_name", record["id"])
        for record in store.list(include_archived=True)
    }
    return build_timeline(live, names)


register_object_list(
    router,
    field="pol_segments",
    path="segments",
    model=PatternOfLifeSegment,
    update_model=PatternOfLifeSegmentUpdate,
    plural="segments",
    not_found=SEGMENT_NOT_FOUND,
)
