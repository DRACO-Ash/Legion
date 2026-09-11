"""The compendium's classification posture, held in one place.

Ash's decision, 11 September 2026, answering the open question in
`deliverable/01-BUILD-SPECIFICATION.md` section 5: **keep it unclassified,
derived from publicly available information only.**

The wording below is Ash's, deliberately. Classification markings are not
invented, inferred or elaborated here: if a different marking or a caveat
scheme is ever needed, it comes from the person who owns that decision, not
from this file.

Why this is a module rather than a line in the documentation. The house rule
this project keeps relearning is that anything load-bearing has to be
enforced, not described. A note saying "open sources only" constrains nobody.
The one place the rule can actually be broken is `internal_assessment`: every
other source class names something published, but an analyst's own assessment
is opaque about what it reasons from. So that class carries the same burden a
FACT does, and must name the public material behind it. That is the whole
enforceable part of the decision, and it is enforced in `Claim`.
"""

from __future__ import annotations

# The marking, in the decision-maker's own words.
CLASSIFICATION = "UNCLASSIFIED"
HANDLING = "Derived from publicly available information only."

# What the interface shows, so one string cannot drift from another.
CLASSIFICATION_BANNER = f"{CLASSIFICATION} // {HANDLING}"

# Source classes that name something already published. An analyst can follow
# the citation to the material itself, which is what makes the posture
# checkable rather than asserted.
PUBLIC_SOURCE_CLASSES = frozenset(
    {
        "official_gov",
        "peer_reviewed",
        "think_tank",
        "commercial_ssa",
        "press",
        "catalogue",
        "state_media",
    }
)

# The one class that is opaque about its inputs, and so has to declare them.
DERIVED_SOURCE_CLASS = "internal_assessment"

DERIVED_NEEDS_CITATION = (
    "An internal assessment must cite the publicly available material it is "
    "derived from. This deployment is unclassified and open-source derived, "
    "so an assessment that cannot name its public basis cannot be stored."
)
